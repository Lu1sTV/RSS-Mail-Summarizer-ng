"""
Dieses Modul enthält alle Funktionen, die Artikel in die Datenbank schreiben oder diese abrufen.
Hier wird die Verbindung zu Firestore hergestellt und die Speicherung,
Verarbeitung und der Abruf von Website- und Alert-Daten verwaltet.
Es enthält Funktionen zum Hinzufügen neuer Links, Speichern von Zusammenfassungen,
Abrufen ungesendeter Artikel, Markieren als gesendet sowie Hilfsfunktionen wie
das Erkennen von Duplikaten und Unterscheidung zwischen normalen und Alert-Links.
"""

# package imports
import os
import json
from dotenv import load_dotenv
from google.cloud import secretmanager
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from urllib.parse import urlparse, parse_qs, unquote
import re
from datetime import datetime
from utils.logger import logger

load_dotenv()
SERVICE_ACCOUNT_KEY_PATH = "serviceAccountKey.json"

print("ENV KEYS:", list(os.environ.keys()))
print("RSS_FIREBASE_KEY exists?", "RSS_FIREBASE_KEY" in os.environ)

def get_firebase_credentials():
    secret_env = "RSS_FIREBASE_KEY"

    if secret_env in os.environ:
        logger.info("Firebase-Service-Account wird aus Umgebungsvariable geladen.")
        try:
            service_account_info = json.loads(os.environ[secret_env])
            return credentials.Certificate(service_account_info)
        except Exception as e:
            logger.error(f"Fehler beim Laden des Secrets aus der Umgebungsvariable: {e}")
            raise
    else:
        logger.warning(
            f"Umgebungsvariable {secret_env} nicht gefunden – "
            f"verwende lokale Datei {SERVICE_ACCOUNT_KEY_PATH}."
        )
        try:
            return credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
        except Exception as e:
            logger.error(f"Konnte lokale Datei {SERVICE_ACCOUNT_KEY_PATH} nicht laden: {e}")
            raise


def initialize_firebase():
    if not firebase_admin._apps:
        cred = get_firebase_credentials()
        initialize_app(cred)
        logger.info("Firebase erfolgreich initialisiert.")
    else:
        logger.debug("Firebase war bereits initialisiert – überspringe.")



initialize_firebase()

# Firestore-Client wird erstellt
db = firestore.client()


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
    logger.info(f"Datensatz aktualisiert: {url}")


# Prüft, ob eine URL bereits in der Datenbank existiert
def is_duplicate_url(url):
    doc = db.collection("website").document(safe_url(url)).get()
    return doc.exists


# Holt alle Artikel, die noch nicht per Mail gesendet wurden
def get_unsent_entries():
    logger.info("Lade Einträge aus Firestore mit mail_sent=False ...")
    try:
        query = db.collection("website").where("mail_sent", "==", False).stream()
    except Exception as e:
        logger.error(f"Fehler beim Abrufen der Einträge: {e}")
        return []

    entries = []
    for doc in query:
        data = doc.to_dict() or {}
        url = data.get("url")

        if not url or not isinstance(url, str):
            logger.warning(f"Überspringe Eintrag ohne gültige URL: {data}")
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
        logger.debug(f"Hinzugefügt: {entry['url']} (Kategorie: {entry['category']}, Subkategorie: {entry['subcategory']})")

    return entries


# Markiert eine übergebene Liste von Artikeln in der Datenbank als gesendet
def mark_as_sent(entries):
    for entry in entries:
        url = entry.get("url")
        if not url:
            logger.warning(f"Kein URL-Feld für Eintrag: {entry}")
            continue
        db.collection("website").document(safe_url(url)).update({"mail_sent": True})

    # logger.info(f"{len(entries)} Einträge wurden als gesendet markiert.")


# Fügt eine neue unverarbeitete URL in die Datenbank ein
def add_url_to_website_collection(url):
    doc_ref = db.collection("website").document(safe_url(url))
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.set(
            {
                "url": url,
                "processed": False,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            }
        )
        logger.info(f"Neue URL gespeichert: {url}")
    else:
        logger.debug(f"URL bereits vorhanden (wird ignoriert): {url}")


# Fügt oder aktualisiert eine Alert-URL mit Kategorie in der Datenbank
def add_alert_to_website_collection(url, category):
    doc_ref = db.collection("website").document(safe_url(url))
    update_data = {
        "url": url,
        "alert": True,
        "category": category,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        "processed": False
    }
    doc_ref.set(update_data, merge=True)
    logger.info(f"URL gespeichert/aktualisiert: {url} (Kategorie: {category})")


# Holt alle unverarbeiteten URLs (inkl. Info ob es sich um Alerts handelt)
def get_unprocessed_urls():
    urls = []
    for doc in db.collection("website").where("processed", "==", False).stream():
        data = doc.to_dict()
        urls.append(
            {
                "url": data.get("url"),
                "alert": data.get("alert", False),
            }
        )
    return urls


# Prüft, ob eine bestimmte URL als Alert markiert ist
def is_alert(url):
    doc_ref = db.collection("website").document(safe_url(url)).get()
    if doc_ref.exists:
        data = doc_ref.to_dict()
        return data.get("alert", False)
    return False


# Holt die höchste Toot-ID aus Firestore
def get_last_toot_id():
    docs = (
        db.collection("mastodon_toots")
        .order_by("toot_id", direction=firestore.Query.DESCENDING)
        .limit(1)
        .stream()
    )

    for doc in docs:
        return doc.to_dict().get("toot_id")

    return None


# Speichert die aktuellste Toot-ID in Firestore
def save_last_toot_id(toot_id: int):
    data = {
        "toot_id": int(toot_id),
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    }
    db.collection("mastodon_toots").add(data)
    logger.info(f"Neue Toot-ID gespeichert: {toot_id}")

