import os
import re
import sys
import json
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse, parse_qs, unquote

import firebase_admin
from firebase_admin import credentials, firestore

# Logger Setup
logger = logging.getLogger("alerts_processor")
logger.setLevel(getattr(logging, os.environ.get("LOG_LEVEL", "DEBUG").upper(), logging.DEBUG))

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


def safe_url(url: str) -> str:
    """Extrahiert echte URL aus Google Redirect und macht sie Firestore-kompatibel."""
    parsed = urlparse(url)
    qs = parse_qs(parsed.query)
    target = qs.get("url")
    if target:
        url = unquote(target[0])

    url = url.strip()
    url = re.sub(r"[^a-zA-Z0-9_-]", "-", url)
    url = re.sub(r"-+", "-", url)
    url = url.strip("-")

    return url


class FirestoreDatabase:
    """Firestore access layer for the alerts pipeline."""

    def __init__(self) -> None:
        try:
            key_json: Optional[str] = os.environ.get("RSS_FIREBASE_KEY")
            if key_json:
                logger.debug("Firebase: using env secret.")
                cred = credentials.Certificate(json.loads(key_json))
            else:
                logger.error("Firebase key is missing.")
                raise RuntimeError("RSS_FIREBASE_KEY environment variable is missing but required.")

            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()

            # Quick connectivity check
            self.db.collection("website").limit(1).get()
            logger.info("Firestore connected.")
        except Exception as e:
            logger.error(f"Firestore connection failed: {e}")
            raise RuntimeError(f"Firestore Connection failed: {str(e)}")

    def save_url(self, url: str, alert_name: str) -> None:
        """Save an alert URL to Firestore (einheitliches Schema)."""
        try:
            doc_id = safe_url(url)
            self.db.collection("website").document(doc_id).set({
                "url": url,
                "source": "alerts",
                "feed": alert_name,
                "processed": False,
                "mail_sent": False,
                "podcast_generated": False,
                "time_stamp": datetime.now(timezone.utc),
                "category": "",
                "sub_category": "",
            }, merge=True)
            logger.debug(f"Saved URL: {url} (feed: {alert_name})")
        except Exception as e:
            logger.error(f"Failed to save URL {url}: {e}")
            raise
