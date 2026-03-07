import os
import sys
import json
import logging
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore

# Logger Setup
logger = logging.getLogger("alerts_processor")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)


class FirestoreDatabase:
    """Firestore access layer for the alerts pipeline."""

    def __init__(self) -> None:
        try:
            key_json: Optional[str] = os.environ.get("RSS_FIREBASE_KEY")
            if key_json:
                logger.debug("Firebase: using env secret.")
                cred = credentials.Certificate(json.loads(key_json))
            else:
                logger.debug("Firebase: using local key file.")
                key_path: str = os.path.join(os.path.dirname(__file__), "keys", "serviceAccountKey.json")
                cred = credentials.Certificate(key_path)

            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()

            # Quick connectivity check
            self.db.collection("website").limit(1).get()
            logger.info("Firestore connected.")
        except Exception as e:
            logger.error(f"Firestore connection failed: {e}")
            raise RuntimeError(f"Firestore Connection failed: {str(e)}")

    def save_url(self, url: str, category: str) -> None:
        """Save an alert URL to Firestore with merge."""
        try:
            doc_id: str = url.replace("https://", "").replace("http://", "").replace("/", "-")[:250]
            self.db.collection("website").document(doc_id).set({
                "url": url,
                "category": category,
                "alert": True,
                "processed": False,
                "podcast_generated": False,
                "timestamp": firestore.SERVER_TIMESTAMP,
            }, merge=True)
            logger.debug(f"Saved URL: {url} (category: {category})")
        except Exception as e:
            logger.error(f"Failed to save URL {url}: {e}")
            raise
