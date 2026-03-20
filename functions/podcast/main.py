import os
import re
import sys
import json
import base64
import logging
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse, parse_qs

import functions_framework
from google.cloud import texttospeech, storage
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from google import genai
from google.genai import types

from config import PodcastConfig
from database import FirestoreDatabase

# Logger Setup
logger = logging.getLogger("podcast_generator")
logger.setLevel(getattr(logging, os.environ.get("LOG_LEVEL", "DEBUG").upper(), logging.DEBUG))

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
        key: Optional[str] = os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError("GEMINI_API_KEY environment variable is missing.")
        return key.strip()

    @staticmethod
    def get_gmail_service() -> Any:
        """Build Gmail API service from token secret or local token file."""
        scopes = ["https://www.googleapis.com/auth/gmail.modify"]
        token_json_str: Optional[str] = os.environ.get("GMAIL_TOKEN_JSON")
        creds: Optional[Credentials] = None

        if token_json_str:
            try:
                creds_info = json.loads(token_json_str)
                creds = Credentials.from_authorized_user_info(creds_info, scopes)
            except Exception as exc:
                logger.error(f"Invalid GMAIL_TOKEN_JSON: {exc}")

        if creds is None:
            local_token_paths = [
                os.path.join(os.path.dirname(__file__), "keys", "token.json"),
                os.path.join(os.path.dirname(__file__), "..", "..", "keys", "token.json"),
            ]
            for token_path in local_token_paths:
                if os.path.exists(token_path):
                    creds = Credentials.from_authorized_user_file(token_path, scopes)
                    break

        if not creds:
            raise RuntimeError("No Gmail token found. Set GMAIL_TOKEN_JSON or provide keys/token.json.")

        if not creds.valid:
            if creds.expired and creds.refresh_token:
                from google.auth.transport.requests import Request
                creds.refresh(Request())
            else:
                raise RuntimeError("Gmail token is invalid and cannot be refreshed.")

        return build("gmail", "v1", credentials=creds)


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
        """Scrape web pages via BeautifulSoup and summarize YouTube videos via Gemini."""
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
                char_count = len(clean_text)
                content_collection.append(f"Quelle: {url}\nInhalt: {clean_text[:PodcastConfig.MAX_CONTENT_CHARS]}")
                logger.info(f"  -> {char_count} chars fetched for {url}")
            except Exception as e:
                logger.error(f"Fetch failed ({url}): {e}")

        for url in youtube_urls:
            logger.info(f"Fetching YT: {url}")
            try:
                clean_url: str = self._clean_youtube_url(url)
                youtube_video = types.Part.from_uri(file_uri=clean_url, mime_type="video/*")
                response = self.client.models.generate_content(
                    model=PodcastConfig.GEMINI_MODEL,
                    contents=[
                        youtube_video,
                        "Erstelle eine sehr ausfuehrliche, detaillierte Zusammenfassung dieses Videos. "
                        "Nenne alle wichtigen Argumente, Fakten und Diskussionspunkte, damit daraus "
                        "spaeter ein tiefergehender Podcast erstellt werden kann."
                    ]
                )
                text: str = response.text.strip()
                char_count = len(text)
                content_collection.append(f"Quelle (YouTube): {url}\nInhalt: {text}")
                logger.info(f"  -> {char_count} chars fetched for {url}")
            except Exception as e:
                logger.error(f"YT fetch failed ({url}): {e}")

        return content_collection

    @staticmethod
    def _strip_urls(text: str) -> str:
        """Remove leftover URLs from script text."""
        return re.sub(r"https?://\S+", "", text).strip()

    @staticmethod
    def _estimate_duration_min(script: List[str]) -> float:
        """Estimate podcast duration in minutes based on word count."""
        total_words = sum(len(passage.split()) for passage in script)
        return total_words / PodcastConfig.TTS_WORDS_PER_MINUTE

    def generate_script(self, content_collection: List[str]) -> List[str]:
        """Generate a two-voice script via Gemini (returns JSON list) with length validation and retry."""
        if not content_collection:
            logger.warning("No content for script generation.")
            return []

        content_text: str = "\n\n---\n\n".join(content_collection)

        system_instruction: str = (
            "Du erstellst ein langes, detailliertes deutsches Podcast-Skript fuer zwei Moderatoren (Sprecher 1 und Sprecher 2) "
            f"basierend auf den uebergebenen Rohtexten. Ziel ist eine Podcast-Laenge von mindestens {PodcastConfig.MIN_PODCAST_MINUTES} "
            f"bis {PodcastConfig.MAX_PODCAST_MINUTES} Minuten. "
            "Erstelle mindestens 50 Passagen. Behandle jede Quelle ausfuehrlich in 2-3 Passagen. "
            "Gehe tief in die Themen ein, lass die Moderatoren die Inhalte diskutieren, Vor- und Nachteile abwaegen und Details aus den Texten erklaeren. "
            "Kuerze NICHT ab.\n\n"
            "WICHTIG: Gib ausschliesslich ein valides JSON-Array zurueck. Jedes Element im Array muss ein reiner String sein, der den gesprochenen Text enthaelt.\n"
            "Der Text muss abwechselnd von Sprecher 1 und Sprecher 2 gelesen werden. Keine Rollennamen oder Praefixe (wie 'Sprecher 1:') im String. "
            "Keine URLs im Text."
        )

        script: List[str] = []
        for attempt in range(1, PodcastConfig.MAX_SCRIPT_RETRIES + 1):
            logger.info(f"Generating script via Gemini (attempt {attempt}/{PodcastConfig.MAX_SCRIPT_RETRIES})...")
            try:
                extra_hint = ""
                if attempt > 1:
                    extra_hint = (
                        f"\n\nWICHTIG: Der vorherige Versuch war zu kurz "
                        f"(ca. {self._estimate_duration_min(script):.1f} min). "
                        f"Erstelle mindestens {PodcastConfig.MIN_PODCAST_MINUTES} Minuten Inhalt! "
                        "Mehr Passagen, mehr Details, NICHT abkuerzen."
                    )

                response = self.client.models.generate_content(
                    model=PodcastConfig.GEMINI_MODEL,
                    contents=f"Nachrichten-Rohtexte:\n{content_text}{extra_hint}",
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        temperature=PodcastConfig.SCRIPT_TEMPERATURE,
                        max_output_tokens=PodcastConfig.MAX_OUTPUT_TOKENS,
                        response_mime_type="application/json",
                    )
                )
                script = json.loads(response.text.strip())

                # Strip URLs from each passage
                script = [self._strip_urls(p) for p in script if self._strip_urls(p)]

                estimated_min = self._estimate_duration_min(script)
                total_words = sum(len(p.split()) for p in script)
                logger.info(
                    f"Script: {len(script)} passages, {total_words} words, "
                    f"~{estimated_min:.1f} min estimated duration."
                )

                if estimated_min >= PodcastConfig.MIN_PODCAST_MINUTES:
                    if estimated_min > PodcastConfig.MAX_PODCAST_MINUTES:
                        logger.warning(
                            f"Script exceeds target: ~{estimated_min:.1f} min "
                            f"(max {PodcastConfig.MAX_PODCAST_MINUTES} min)."
                        )
                    return script

                logger.warning(
                    f"Script too short: ~{estimated_min:.1f} min "
                    f"(min {PodcastConfig.MIN_PODCAST_MINUTES} min). Retrying..."
                )

            except json.JSONDecodeError as e:
                logger.error(f"Gemini returned invalid JSON: {e}")
                if attempt == PodcastConfig.MAX_SCRIPT_RETRIES:
                    raise RuntimeError(f"Invalid JSON from Gemini after {attempt} attempts: {e}")
            except Exception as e:
                logger.error(f"Script generation failed: {e}")
                raise

        # Return the best we got after all retries
        logger.warning("Max retries reached – using last generated script.")
        return script


class AudioService:
    """TTS synthesis and GCS upload."""

    VOICES: List[str] = [PodcastConfig.TTS_HOST_VOICE, PodcastConfig.TTS_GUEST_VOICE]

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
            sample_rate_hertz=PodcastConfig.TTS_SAMPLE_RATE
        )

        combined_audio: bytes = b""
        for index, text in enumerate(script):
            logger.debug(f"TTS passage {index + 1}/{len(script)}...")
            synthesis_input = texttospeech.SynthesisInput(text=text)
            voice_params = texttospeech.VoiceSelectionParams(
                language_code=PodcastConfig.TTS_LANGUAGE,
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

    def generate_signed_url(self, filename: str) -> str:
        """Generate a V4 signed URL for the uploaded MP3."""
        creds: service_account.Credentials = GCPAuthService.get_credentials()
        storage_client = storage.Client(credentials=creds, project=creds.project_id)
        bucket = storage_client.bucket(PodcastConfig.GCS_BUCKET_NAME)
        blob = bucket.blob(filename)
        url: str = blob.generate_signed_url(
            version="v4",
            expiration=timedelta(days=PodcastConfig.SIGNED_URL_EXPIRY_DAYS),
            method="GET",
        )
        logger.info(f"Signed URL generated (expires in {PodcastConfig.SIGNED_URL_EXPIRY_DAYS}d): {filename}")
        return url


class PodcastMailService:
    """Sends podcast download link via Gmail API."""

    def __init__(self) -> None:
        if not PodcastConfig.SENDER_EMAIL or not PodcastConfig.RECIPIENT_EMAIL:
            raise RuntimeError("SENDER_EMAIL and RECIPIENT_EMAIL environment variables are required.")

    def send_podcast_mail(self, podcast_filename: str, signed_url: str) -> None:
        """Send podcast email with a signed download link."""
        from email.mime.text import MIMEText

        html_body = (
            f"<h2>Neuer Podcast vom {datetime.now().strftime('%d.%m.%Y')}</h2>"
            f"<p>Datei: {podcast_filename}</p>"
            f'<p><a href="{signed_url}">Podcast herunterladen</a></p>'
            f"<p><small>Der Link ist {PodcastConfig.SIGNED_URL_EXPIRY_DAYS} Tage gueltig.</small></p>"
        )

        msg = MIMEText(html_body, "html", "utf-8")
        msg["From"] = PodcastConfig.SENDER_EMAIL
        msg["To"] = PodcastConfig.RECIPIENT_EMAIL
        msg["Subject"] = f"Neuer Podcast {datetime.now().strftime('%Y-%m-%d')}"

        gmail_service = GCPAuthService.get_gmail_service()
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        gmail_service.users().messages().send(userId="me", body={"raw": raw_message}).execute()
        logger.info(f"Podcast mail sent to {PodcastConfig.RECIPIENT_EMAIL} with signed URL for {podcast_filename}.")


@functions_framework.http
def podcast_trigger(request: Any) -> Tuple[str, int]:
    """HTTP entry point – runs the full podcast pipeline."""
    logger.info("Starting podcast_trigger.")
    try:
        db = FirestoreDatabase()
        ai_service = PodcastAIService(GCPAuthService.get_gemini_api_key())
        audio_service = AudioService()
        mail_service = PodcastMailService()

        candidates: List[Tuple[Any, Dict[str, Any]]] = db.fetch_entries()

        if not candidates:
            logger.info("No new entries found.")
            return json.dumps({"status": "ok", "resource": "podcast", "details": {"message": "No new entries found."}}, indent=2), 200

        doc_refs: List[Any] = [ref for ref, _ in candidates]
        entries: List[Dict[str, Any]] = [data for _, data in candidates]
        urls: List[str] = [e.get("url") for e in entries if e.get("url")]
        logger.info(f"Processing {len(urls)} URLs.")

        raw_content: List[str] = ai_service.fetch_raw_content(urls)
        script: List[str] = ai_service.generate_script(raw_content)
        filename: Optional[str] = audio_service.generate_and_upload(script)

        if not filename:
            raise RuntimeError("Podcast generation did not produce a file.")

        signed_url: str = audio_service.generate_signed_url(filename)
        mail_service.send_podcast_mail(filename, signed_url)

        db.mark_as_podcast_generated(doc_refs)

        estimated_min = PodcastAIService._estimate_duration_min(script)
        response_data: Dict[str, Any] = {
            "status": "success",
            "resource": "podcast",
            "details": {
                "file": filename,
                "entries_processed": len(doc_refs),
                "script_passages": len(script),
                "estimated_duration_min": round(estimated_min, 1),
                "mail_sent_to": PodcastConfig.RECIPIENT_EMAIL,
            }
        }
        logger.info("Execution completed.")
        return json.dumps(response_data, indent=2), 200

    except RuntimeError as re:
        logger.critical(f"Init error: {re}")
        return json.dumps({"status": "error", "resource": "podcast", "details": {"message": str(re)}}, indent=2), 500
    except Exception as e:
        logger.critical(f"Server error: {e}", exc_info=True)
        return json.dumps({"status": "error", "resource": "podcast", "details": {"message": "Internal Server Error"}}, indent=2), 500


if __name__ == "__main__":
    podcast_trigger()
