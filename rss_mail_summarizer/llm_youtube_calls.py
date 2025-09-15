"""
Dieses Modul stellt Funktionen bereit, um YouTube-Videos mit Vertex AI (Gemini) 
automatisch zusammenzufassen und zu kategorisieren. 
Es unterstützt sowohl normale Links als auch Google-Alert-Links. 
Die Zugangsdaten für Vertex AI können entweder lokal aus einer JSON-Datei 
oder in Google Cloud über den Secret Manager verwaltet werden. 
Zusätzlich werden YouTube-URLs normalisiert, damit das Modell sie zuverlässig erkennt. 
Alle relevanten Schritte und Fehler werden im Log (auf Deutsch) dokumentiert.
"""

# Package Imports
import re
from google.oauth2 import service_account
from google.cloud import secretmanager
from dotenv import load_dotenv
import os
from urllib.parse import urlparse, parse_qs, unquote
import sys
from google import genai
from google.genai import types


# Eigene Funktionen
from utils.logger import logger

load_dotenv()

# Projekt-ID aus Umgebungsvariablen
PROJECT_ID = os.environ.get("PROJECT_ID")

# Secret-ID für das Service Account JSON
SERVICE_ACCOUNT_SECRET_ID = "rss-vertex-ai-key"
SERVICE_ACCOUNT_LOCAL_FILE = "utils/serviceaccountkey.json"


# Funktion zum Zugriff auf Secrets
def access_secret(secret_id: str, project_id: str) -> str:
    logger.debug(f"Greife auf Secret '{secret_id}' im Projekt '{project_id}' zu...")
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    logger.info(f"Secret '{secret_id}' erfolgreich aus Secret Manager abgerufen.")
    return response.payload.data.decode("UTF-8")


# Service-Account-Credentials laden (Cloud oder lokal)
def get_service_account_credentials():
    if PROJECT_ID:
        try:
            logger.info("Versuche Service Account JSON aus Secret Manager zu laden...")
            sa_json = access_secret(SERVICE_ACCOUNT_SECRET_ID, PROJECT_ID)

            with open("/tmp/serviceaccount.json", "w") as f:
                f.write(sa_json)

            creds = service_account.Credentials.from_service_account_file(
                "/tmp/serviceaccount.json",
                scopes=["https://www.googleapis.com/auth/cloud-platform"]
            )
            logger.info("Service Account erfolgreich aus Secret Manager geladen.")
            return creds
        except Exception as e:
            logger.warning(f"Konnte Secret nicht abrufen (Grund: {e}). Fallback auf lokale Datei...")

    # Fallback auf lokale Datei
    logger.info("Verwende lokales Service Account File.")
    return service_account.Credentials.from_service_account_file(
        SERVICE_ACCOUNT_LOCAL_FILE,
        scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )


# Client initialisieren
creds = get_service_account_credentials()
client = genai.Client(
    vertexai=True,
    project=PROJECT_ID,
    location="us-central1",
    credentials=creds
)

youtube_model_id = "gemini-2.5-flash"

# Normalisierung von YouTube URLs, damit sie von Gemini erkannt werden
def clean_youtube_url(url: str) -> str:
    logger.debug(f"Starte Normalisierung der URL: {url}")
    url = url.strip().rstrip(":")
    parsed = urlparse(url)

    # Google Redirect Wrapper behandeln
    if "google.com" in parsed.netloc and "youtube.com" in url:
        qs = parse_qs(parsed.query)
        if "url" in qs:
            cleaned_url = unquote(qs["url"][0])
            logger.info(f"Google-Redirect erkannt. Normalisierte URL: {cleaned_url}")
            return clean_youtube_url(cleaned_url)

    # HTML-encoded Ampersand ersetzen
    url = url.replace("&amp;", "&")

    parsed = urlparse(url)

    # Kurze youtu.be Links behandeln
    if "youtu.be" in parsed.netloc:
        video_id = parsed.path.lstrip("/")
        normalized_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info(f"Kurze youtu.be URL erkannt. Normalisierte URL: {normalized_url}")
        return normalized_url

    # Vollständige YouTube-Links behandeln (nur v= behalten)
    if "youtube.com" in parsed.netloc:
        qs = parse_qs(parsed.query)
        if "v" in qs:
            normalized_url = f"https://www.youtube.com/watch?v={qs['v'][0]}"
            logger.info(f"Vollständige YouTube URL normalisiert: {normalized_url}")
            return normalized_url

    logger.debug(f"URL nach Normalisierung: {url}")
    return url


def summarise_youtube_videos(youtube_urls):
    """
    Fasst YouTube-Videos mit Gemini 2.5 Flash zusammen und kategorisiert sie.
    Gibt ein dict zurück: {url: {summary, reading_time, category}}
    """
    results = {}
    categories = [
        "Technology and Gadgets", "Artificial Intelligence", "Programming and Development",
        "Politics", "Business and Finance", "Sports", "Education and Learning",
        "Health and Wellness", "Entertainment and Lifestyle", "Travel and Tourism"
    ]

    for i, url in enumerate(youtube_urls):
        url = url.rstrip(":")
        try:
            logger.info(f"Verarbeite YouTube-Video {i+1}/{len(youtube_urls)}: {url}")
            clean_url = clean_youtube_url(url)
            logger.debug(f"Bereite Video-Part für Gemini vor: {clean_url}")
            youtube_video = types.Part.from_uri(file_uri=clean_url, mime_type="video/*")

            prompt_text = f"""
Du bist ein Assistent, der YouTube-Videos zusammenfasst und kategorisiert.
Anweisungen:
1. Fasse das Video in 2-3 Sätzen zusammen.
2. Schätze die Betrachtungszeit in Minuten.
3. Ordne das Video einer der folgenden Kategorien zu:
   {', '.join(categories)}
   Wenn keine Kategorie passt, gib 'Uncategorized' zurück.

Format:
Summary: <Zusammenfassung>
Reading Time: <geschätzte Minuten>
Category: <Kategorie>
"""

            contents = [youtube_video, types.Part.from_text(text=prompt_text)]

            generate_config = types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=1024,
                response_modalities=["TEXT"],
            )

            logger.debug("Sende Anfrage an Vertex AI Gemini...")
            response = client.models.generate_content(
                model=youtube_model_id,
                contents=contents,
                config=generate_config
            )
            logger.info("Antwort von Gemini erhalten.")

            text = response.text.strip()
            logger.debug(f"Gemini-Ausgabe:\n{text}")

            summary_match = re.search(r"Summary:\s*(.+)", text, re.IGNORECASE)
            reading_time_match = re.search(r"Reading\s*Time:\s*(\d+)", text, re.IGNORECASE)
            category_match = re.search(r"Category:\s*(.+)", text, re.IGNORECASE)

            results[url] = {
                "summary": summary_match.group(1).strip() if summary_match else None,
                "reading_time": int(reading_time_match.group(1)) if reading_time_match else None,
                "category": category_match.group(1).strip() if category_match else "Uncategorized",
            }
            logger.info(f"Video erfolgreich verarbeitet: {url}")

        except Exception as e:
            logger.error(f"Fehler bei Verarbeitung des Videos {url}: {e}")
            results[url] = {"summary": None, "reading_time": None, "category": None}

    return results


def summarise_youtube_alerts(youtube_urls):
    """
    Fasst YouTube-Alert-Videos zusammen (kürzerer Prompt).
    Gibt dict zurück: {url: {summary, reading_time}}
    """
    results = {}

    for i, url in enumerate(youtube_urls):
        url = url.rstrip(":")
        try:
            logger.info(f"Verarbeite YouTube Alert {i+1}/{len(youtube_urls)}: {url}")
            clean_url = clean_youtube_url(url)
            logger.debug(f"Bereite Video-Part für Gemini vor: {clean_url}")
            youtube_video = types.Part.from_uri(file_uri=clean_url, mime_type="video/*")

            prompt_text = """
Du bist ein Assistent, der YouTube-Videos aus Google Alerts zusammenfasst.
Anweisungen:
1. Fasse das Video in 2-3 Sätzen zusammen.
2. Schätze die Betrachtungszeit in Minuten.

Format:
Summary: <Zusammenfassung>
Reading Time: <geschätzte Minuten>
"""

            contents = [youtube_video, types.Part.from_text(text=prompt_text)]

            generate_config = types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=1024,
                response_modalities=["TEXT"],
            )

            logger.debug("Sende Anfrage an Vertex AI Gemini für Alert...")
            response = client.models.generate_content(
                model=youtube_model_id,
                contents=contents,
                config=generate_config
            )
            logger.info("Antwort von Gemini für Alert erhalten.")

            text = response.text.strip()
            logger.debug(f"Gemini-Ausgabe Alert:\n{text}")

            summary_match = re.search(r"Summary:\s*(.+)", text, re.IGNORECASE)
            reading_time_match = re.search(r"Reading\s*Time:\s*(\d+)", text, re.IGNORECASE)

            results[url] = {
                "summary": summary_match.group(1).strip() if summary_match else None,
                "reading_time": int(reading_time_match.group(1)) if reading_time_match else None,
            }
            logger.info(f"Alert erfolgreich verarbeitet: {url}")

        except Exception as e:
            logger.error(f"Fehler bei Verarbeitung des Alerts {url}: {e}")
            results[url] = {"summary": None, "reading_time": None}

    return results
