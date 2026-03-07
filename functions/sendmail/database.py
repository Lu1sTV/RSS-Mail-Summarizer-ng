"""
Datenbankzugriff für die eigenständige `sendmail`-Function.

Einheitliches Schema:
  source, mail_sent, podcast_generated, time_stamp, feed,
  processed, category, sub_category, url
"""

# package imports
import os
import json
from dotenv import load_dotenv
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from urllib.parse import urlparse, parse_qs, unquote
import re
from datetime import datetime, timezone

# lokaler Logger
import logging

# einfacher Logger für dieses Modul
default_logger = logging.getLogger(__name__)

load_dotenv()
SERVICE_ACCOUNT_KEY_PATH = "serviceAccountKey.json"


def get_firebase_credentials():
    secret_env = "RSS_FIREBASE_KEY"

    if secret_env in os.environ:
        default_logger.info("Firebase-Service-Account wird aus Umgebungsvariable geladen.")
        try:
            service_account_info = json.loads(os.environ[secret_env])
            return credentials.Certificate(service_account_info)
        except Exception as e:
            default_logger.error(f"Fehler beim Laden des Secrets aus der Umgebungsvariable: {e}")
            raise
    else:
        default_logger.warning(
            f"Umgebungsvariable {secret_env} nicht gefunden – "
            f"verwende lokale Datei {SERVICE_ACCOUNT_KEY_PATH}."
        )
        try:
            return credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        except Exception as e:
            default_logger.error(f"Konnte lokale Datei {SERVICE_ACCOUNT_KEY_PATH} nicht laden: {e}")
            raise


def initialize_firebase():
    if not firebase_admin._apps:
        cred = get_firebase_credentials()
        initialize_app(cred)
        default_logger.info("Firebase erfolgreich initialisiert.")
    else:
        default_logger.debug("Firebase war bereits initialisiert – überspringe.")


initialize_firebase()

# Firestore-Client wird erstellt
db = firestore.client()


# Die folgenden Funktionen sind identisch zu denen im Hauptrepo

def safe_url(google_url: str) -> str:
    """Extrahiert echte URL aus Google Redirect und macht sie Firestore-kompatibel."""
    parsed = urlparse(google_url)
    qs = parse_qs(parsed.query)
    target = qs.get("url")
    if target:
        url = unquote(target[0])
    else:
        url = google_url

    url = url.strip()
    url = re.sub(r"[^a-zA-Z0-9_-]", "-", url)
    url = re.sub(r"-+", "-", url)
    url = url.strip("-")

    return url


# Fügt Einträge in die Datenbank ein oder aktualisiert bestehende Einträge

def add_datarecord(url, category=None, summary=None, reading_time=None, sub_category=None,
                   mail_sent=False, hn_points=None, processed=None):
    """Aktualisiert einen Eintrag mit LLM-Ergebnissen (einheitliches Schema)."""
    update_data = {
        "processed": True,
        "time_stamp": datetime.now(timezone.utc),
        "url": url,
    }
    if category:
        update_data["category"] = category
    if summary is not None:
        update_data["summary"] = summary
    if reading_time is not None:
        update_data["reading_time"] = reading_time
    if sub_category is not None:
        update_data["sub_category"] = sub_category
    if mail_sent is not None:
        update_data["mail_sent"] = mail_sent
    if hn_points is not None:
        update_data["hn_points"] = hn_points
    if processed is not None:
        update_data["processed"] = processed

    db.collection("website").document(safe_url(url)).set(update_data, merge=True)
    default_logger.info(f"Datensatz aktualisiert: {url}")


# Prüft, ob eine URL bereits in der Datenbank existiert

def is_duplicate_url(url):
    doc = db.collection("website").document(safe_url(url)).get()
    return doc.exists


# Holt alle Artikel, die noch nicht per Mail gesendet wurden

def get_unsent_entries():
    default_logger.info("Lade Einträge aus Firestore mit mail_sent=False ...")
    try:
        query = db.collection("website").where("mail_sent", "==", False).stream()
    except Exception as e:
        default_logger.error(f"Fehler beim Abrufen der Einträge: {e}")
        return []

    entries = []
    for doc in query:
        data = doc.to_dict() or {}
        url = data.get("url")

        if not url or not isinstance(url, str):
            default_logger.warning(f"Überspringe Eintrag ohne gültige URL: {data}")
            continue

        entry = {
            "doc_id": doc.id,
            "url": url,
            "source": data.get("source"),
            "feed": data.get("feed"),
            "category": data.get("category"),
            "summary": data.get("summary"),
            "sub_category": data.get("sub_category"),
            "reading_time": data.get("reading_time"),
            "hn_points": data.get("hn_points"),
            "time_stamp": data.get("time_stamp"),
        }
        entries.append(entry)
        default_logger.debug(f"Hinzugefügt: {entry['url']} (Kategorie: {entry['category']}, Sub-Kategorie: {entry['sub_category']})")

    return entries


# Markiert eine übergebene Liste von Artikeln in der Datenbank als gesendet

def mark_as_sent(entries):
    for entry in entries:
        url = entry.get("url")
        if not url:
            default_logger.warning(f"Kein URL-Feld für Eintrag: {entry}")
            continue
        db.collection("website").document(safe_url(url)).update({"mail_sent": True})

    # logger.info(f"{len(entries)} Einträge wurden als gesendet markiert.")


# Holt alle unverarbeiteten URLs (inkl. Info ob es sich um Alerts handelt)

def get_unprocessed_urls():
    urls = []
    for doc in db.collection("website").where("processed", "==", False).stream():
        data = doc.to_dict()
        urls.append(
            {
                "url": data.get("url"),
                "is_alert": data.get("source") == "alerts",
            }
        )
    return urls


# Prüft, ob eine bestimmte URL als Alert markiert ist (source == "alerts")

def is_alert(url):
    doc_ref = db.collection("website").document(safe_url(url)).get()
    if doc_ref.exists:
        data = doc_ref.to_dict()
        return data.get("source") == "alerts"
    return False
