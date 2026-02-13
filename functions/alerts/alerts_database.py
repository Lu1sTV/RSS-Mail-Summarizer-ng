import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_db_client = None

def get_db():
    global _db_client
    if _db_client is None:
        key_json = os.environ.get("RSS_FIREBASE_KEY")
        
        if not key_json:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            key_path = os.path.join(base_dir, "keys", "serviceAccountKey.json")
            
            if os.path.exists(key_path):
                cred = credentials.Certificate(key_path)
            else:
                raise Exception(f"FEHLER: Weder RSS_FIREBASE_KEY gesetzt noch {key_path} gefunden!")
        else:
            cred_info = json.loads(key_json)
            cred = credentials.Certificate(cred_info)

        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        _db_client = firestore.client()
    
    return _db_client

def save_alert_url(url, category):
    try:
        db = get_db()
        
        doc_id = url.replace("https://", "").replace("http://", "").replace("/", "-")
        if len(doc_id) > 250:
            doc_id = doc_id[:250]

        doc_ref = db.collection("website").document(doc_id)
        
        doc_ref.set({
            "url": url,
            "category": category,
            "alert": True,
            "processed": False,
            "timestamp": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        logger.info(f"DB: Link gespeichert -> {url}")
        return True
    except Exception as e:
        logger.error(f"DB FEHLER beim Speichern von {url}: {e}")
        return False