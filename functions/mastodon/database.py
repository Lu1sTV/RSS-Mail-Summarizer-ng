"""
Dieses Modul kapselt alle Firestore-Zugriffe fuer die Mastodon Function.
"""

import os
import logging
from datetime import datetime
import re
from urllib.parse import urlparse, parse_qs, unquote
from dotenv import load_dotenv
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app

load_dotenv()

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("app_logger")

def initialize_firebase():
    if not firebase_admin._apps:
        if os.getenv('K_SERVICE'):
            logger.info("Cloud-Umgebung erkannt: Nutze Application Default Credentials.")
            initialize_app()
        else:
            SERVICE_ACCOUNT_KEY_PATH = "serviceAccountKey.json"
            if os.path.exists(SERVICE_ACCOUNT_KEY_PATH):
                logger.info(f"Lokale Umgebung: Nutze {SERVICE_ACCOUNT_KEY_PATH}")
                cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)
                initialize_app(cred)
            else:
                logger.error("Keine Credentials gefunden (weder Cloud noch lokale Datei)!")
                raise FileNotFoundError("Service Account Key fehlt für lokale Ausführung.")
    else:
        logger.debug("Firebase war bereits initialisiert.")

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

class FirestoreRepository:
    """Kapselt alle Firestore-Operationen fuer die Mastodon Function."""

    def __init__(self):
        initialize_firebase()
        self.db = firestore.client()

    def add_url_to_website_collection(self, url, toot_text=None, toot_url=None, toot_date=None):
            """Speichert eine neu gefundene URL inkl. Mastodon-Metadaten in der DB."""
            doc_ref = self.db.collection("website").document(safe_url(url))
            doc = doc_ref.get()
            
            if not doc.exists:
                # Basis-Daten
                data = {
                    "url": url,
                    "processed": False,
                    "mail_sent": False,
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
                    "source": "mastodon"
                }
                
                # Neue Felder hinzufügen, falls sie mitgegeben wurden
                if toot_text:
                    data["toot_text"] = toot_text
                if toot_url:
                    data["toot_url"] = toot_url
                if toot_date:
                    data["toot_date"] = toot_date
    
                doc_ref.set(data)
                logger.info(f"Neue URL gespeichert: {url}")
            else:
                logger.debug(f"URL bereits vorhanden (wird ignoriert): {url}")

    def get_last_toot_id(self):
        """Holt die ID des zuletzt verarbeiteten Toots, um Duplikate zu vermeiden."""
        docs = (
            self.db.collection("mastodon_toots")
            .order_by("toot_id", direction=firestore.Query.DESCENDING)
            .limit(1)
            .stream()
        )

        for doc in docs:
            return doc.to_dict().get("toot_id")

        return None

    def save_last_toot_id(self, toot_id: int):
        """Speichert die neueste gelesene Toot-ID."""
        data = {
            "toot_id": int(toot_id),
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
        }
        self.db.collection("mastodon_toots").add(data)
        logger.info(f"Neue Toot-ID gespeichert: {toot_id}")