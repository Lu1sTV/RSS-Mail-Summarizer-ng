import os
import sys
import json
import logging
import traceback
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs

import functions_framework
from google.cloud import texttospeech, storage
from google.oauth2 import service_account

from google import genai
from google.genai import types

from config import PodcastConfig
from database import FirestoreDatabase

# Logger Setup
logger = logging.getLogger("podcast_generator")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


class GCPAuthService:
    """GCP auth for TTS and Storage."""

    @staticmethod
    def get_credentials() -> service_account.Credentials:
        """Load SA credentials from env or local file."""
        secret_env: str = "RSS_FIREBASE_KEY"
        if secret_env in os.environ:
            return service_account.Credentials.from_service_account_info(json.loads(os.environ[secret_env]))
        key_path: str = os.path.join(os.path.dirname(__file__), "keys", "serviceAccountKey.json")
        return service_account.Credentials.from_service_account_file(key_path)

    @staticmethod
    def get_gemini_api_key() -> str:
        """Get Gemini API key from env."""
        key: Optional[str] = os.getenv("GEMINI_API_KEY") or os.getenv("RSS_VERTEX_AI_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
        return key.strip()


class PodcastAIService:
    """Fetches web content and generates podcast scripts via Gemini."""

    def __init__(self, api_key: str) -> None:
        self.client: genai.Client = genai.Client(api_key=api_key)
        logger.info("PodcastAIService initialized.")

    def _clean_youtube_url(self, url: str) -> str:
        """Normalize YouTube URL variants."""
        url = url.strip().rstrip(":")
        parsed = urlparse(url)
        if "youtu.be" in parsed.netloc:
            return f"https://www.youtube.com/watch?v={parsed.path.lstrip('/')}"
        if "youtube.com" in parsed.netloc:
            qs: Dict[str, List[str]] = parse_qs(parsed.query)
            if "v" in qs:
                return f"https://www.youtube.com/watch?v={qs['v'][0]}"
        return url

    def fetch_raw_content(self, urls: List[str]) -> List[str]:
        """Scrape web pages and summarize YouTube videos."""
        youtube_urls: List[str] = [u for u in urls if "youtube.com" in u or "youtu.be" in u]
        web_urls: List[str] = [u for u in urls if u not in youtube_urls]

        content_collection: List[str] = []
        headers: Dict[str, str] = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }

        for url in web_urls:
            logger.info(f"Fetching web: {url}")
            try:
                res = requests.get(url, headers=headers, timeout=15)
                res.raise_for_status()
                soup: BeautifulSoup = BeautifulSoup(res.content, 'html.parser')
                text: str = ' '.join([p.get_text() for p in soup.find_all(['p', 'article', 'h1', 'h2', 'h3'])])
                clean_text: str = text.replace('\n', ' ').strip()
                content_collection.append(f"Quelle: {url}\nInhalt: {clean_text[:15000]}")
            except Exception as e:
                logger.error(f"Fetch failed ({url}): {e}")

        for url in youtube_urls:
            logger.info(f"Fetching YT: {url}")
            try:
                clean_url: str = self._clean_youtube_url(url)
                youtube_video = types.Part.from_uri(file_uri=clean_url, mime_type="video/*")
                response = self.client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=[
                        youtube_video,
                        "Erstelle eine sehr ausfuehrliche, detaillierte Zusammenfassung dieses Videos. "
                        "Nenne alle wichtigen Argumente, Fakten und Diskussionspunkte, damit daraus "
                        "spaeter ein tiefergehender Podcast erstellt werden kann."
                    ]
                )
                content_collection.append(f"Quelle (YouTube): {url}\nInhalt: {response.text.strip()}")
            except Exception as e:
                logger.error(f"YT fetch failed ({url}): {e}")

        return content_collection

    def generate_script(self, content_collection: List[str]) -> List[str]:
        """Generate a two-voice script via Gemini (returns JSON list)."""
        if not content_collection:
            logger.warning("No content for script generation.")
            return []

        logger.info("Generating script via Gemini...")
        content_text: str = "\n\n---\n\n".join(content_collection)

        system_instruction: str = (
            "Du erstellst ein langes, detailliertes deutsches Podcast-Skript fuer zwei Moderatoren (Sprecher 1 und Sprecher 2) "
            "basierend auf den uebergebenen Rohtexten. Ziel ist eine Podcast-Laenge von etwa 15 bis 20 Minuten. "
            "Gehe tief in die Themen ein, lass die Moderatoren die Inhalte diskutieren, Vor- und Nachteile abwaegen und Details aus den Texten erklaeren.\n\n"
            "WICHTIG: Gib ausschliesslich ein valides JSON-Array zurueck. Jedes Element im Array muss ein reiner String sein, der den gesprochenen Text enthaelt.\n"
            "Der Text muss abwechselnd von Sprecher 1 und Sprecher 2 gelesen werden. Keine Rollennamen oder Praefixe (wie 'Sprecher 1:') im String."
        )

        try:
            response = self.client.models.generate_content(
                model="gemini-2.5-flash",
                contents=f"Nachrichten-Rohtexte:\n{content_text}",
                config=types.GenerateContentConfig(
                    system_instruction=system_instruction,
                    temperature=0.7,
                    response_mime_type="application/json",
                )
            )
            script_text: str = response.text.strip()
            return json.loads(script_text)

        except json.JSONDecodeError as e:
            logger.error(f"Gemini returned invalid JSON: {e}")
            raise RuntimeError(f"Invalid JSON from Gemini: {e}")
        except Exception as e:
            logger.error(f"Script generation failed: {e}")
            raise


class AudioService:
    """TTS synthesis and GCS upload."""

    VOICES: List[str] = ["de-DE-Journey-D", "de-DE-Journey-F"]

    def __init__(self) -> None:
        if not PodcastConfig.GCS_BUCKET_NAME:
            raise RuntimeError("GCS_BUCKET_NAME environment variable is missing.")
        logger.info("AudioService initialized.")

    def generate_and_upload(self, script: List[str]) -> Optional[str]:
        """Synthesize all passages and upload the combined MP3."""
        if not script:
            return None

        logger.info("Starting TTS synthesis...")
        creds: service_account.Credentials = GCPAuthService.get_credentials()
        tts_client = texttospeech.TextToSpeechClient(credentials=creds)
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
            sample_rate_hertz=44100
        )

        combined_audio: bytes = b""
        for index, text in enumerate(script):
            logger.debug(f"TTS passage {index + 1}/{len(script)}...")
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice_params = texttospeech.VoiceSelectionParams(
                language_code="de-DE",
                name=self.VOICES[index % 2]
            )
            response = tts_client.synthesize_speech(
                input=synthesis_input, voice=voice_params, audio_config=audio_config
            )
            combined_audio += response.audio_content

        logger.info("TTS done. Uploading to GCS...")

        # Fresh creds to avoid token expiry after long TTS
        fresh_creds: service_account.Credentials = GCPAuthService.get_credentials()
        storage_client = storage.Client(credentials=fresh_creds, project=fresh_creds.project_id)
        bucket = storage_client.bucket(PodcastConfig.GCS_BUCKET_NAME)

        filename: str = f"podcast_{datetime.now().strftime('%Y%m%d_%H%M%S')}.mp3"
        blob = bucket.blob(filename)
        blob.upload_from_string(combined_audio, content_type="audio/mpeg")

        logger.info(f"Uploaded: gs://{PodcastConfig.GCS_BUCKET_NAME}/{filename}")
        return filename


@functions_framework.http
def podcast_trigger(request: Any) -> Tuple[str, int]:
    """HTTP entry point – runs the full podcast pipeline."""
    logger.info("Starting podcast_trigger.")
    try:
        db = FirestoreDatabase()
        ai_service = PodcastAIService(GCPAuthService.get_gemini_api_key())
        audio_service = AudioService()

        candidates: List[Tuple[Any, Dict[str, Any]]] = db.fetch_entries()

        if not candidates:
            logger.info("No new entries found.")
            return json.dumps({"status": "ok", "message": "No new entries found."}, indent=2), 200

        doc_refs: List[Any] = [ref for ref, _ in candidates]
        entries: List[Dict[str, Any]] = [data for _, data in candidates]
        urls: List[str] = [e.get("url") for e in entries if e.get("url")]
        logger.info(f"Processing {len(urls)} URLs.")

        raw_content: List[str] = ai_service.fetch_raw_content(urls)
        script: List[str] = ai_service.generate_script(raw_content)
        filename: Optional[str] = audio_service.generate_and_upload(script)

        db.mark_as_podcast_generated(doc_refs)

        response_data: Dict[str, Any] = {
            "status": "success",
            "file": filename,
            "details": {
                "entries_processed": len(doc_refs),
                "script_passages": len(script)
            }
        }
        logger.info("Execution completed.")
        return json.dumps(response_data, indent=2), 200

    except RuntimeError as re:
        logger.critical(f"Init error: {re}")
        return json.dumps({"error": "Initialization failed", "details": str(re)}, indent=2), 500
    except Exception as e:
        logger.critical(f"Server error: {e}\n{traceback.format_exc()}")
        return json.dumps({"error": "Internal Server Error", "details": str(e), "traceback": traceback.format_exc()}, indent=2), 500


if __name__ == "__main__":
    podcast_trigger()
