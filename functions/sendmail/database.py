"""
Datenbankzugriff für die eigenständige `sendmail`-Function.
Die Originalfunktionen aus dem Hauptprojekt wurden hierher kopiert,
um die Abhängigkeit zum `rss_mail_summarizer` Paket zu eliminieren.
"""

# package imports
import os
import json
from dotenv import load_dotenv
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from urllib.parse import urlparse, parse_qs, unquote
import re
from datetime import datetime

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

def add_datarecord(url, category=None, summary=None, reading_time=None, subcategory=None,
                   mail_sent=False, hn_points=None, processed=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    update_data = {
        "processed": True,
        "timestamp": timestamp,
        "url": url,
    }
    if category:
        update_data["category"] = category
    if summary is not None:
        update_data["summary"] = summary
    if reading_time is not None:
        update_data["reading_time"] = reading_time
    if subcategory is not None:
        update_data["subcategory"] = subcategory
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
            "category": data.get("category"),
            "summary": data.get("summary"),
            "subcategory": data.get("subcategory"),
            "reading_time": data.get("reading_time"),
            "hn_points": data.get("hn_points"),
            "timestamp": data.get("timestamp"),
        }
        entries.append(entry)
        default_logger.debug(f"Hinzugefügt: {entry['url']} (Kategorie: {entry['category']}, Subkategorie: {entry['subcategory']})")

    return entries


# Markiert eine übergebene Liste von Artikeln in der Datenbank als gesendet

def mark_as_sent(entries):
    for entry in entries:
        url = entry.get("url")
        if not url:
            default_logger.warning(f"Kein URL-Feld für Eintrag: {entry}")
            continue
        db.collection("website").document(safe_url(url)).update({"mail_sent": True})
