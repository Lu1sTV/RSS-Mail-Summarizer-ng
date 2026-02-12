# Datei: functions/alerts/alerts_database.py
import os
import json
import logging
import firebase_admin
from firebase_admin import credentials, firestore

# Logger konfigurieren
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_db_client = None

def get_db():
    global _db_client
    if _db_client is None:
        # 1. Cloud-Weg (Environment Variable)
        key_json = os.environ.get("RSS_FIREBASE_KEY")
        
        if not key_json:
            # 2. Lokaler Weg (Datei im keys/ Ordner)
            base_dir = os.path.dirname(os.path.abspath(__file__))
            key_path = os.path.join(base_dir, "keys", "serviceAccountKey.json")
            
            if os.path.exists(key_path):
                # logger.info("DB: Lade Key aus lokaler Datei...")
                cred = credentials.Certificate(key_path)
            else:
                raise Exception(f"FEHLER: Weder RSS_FIREBASE_KEY gesetzt noch {key_path} gefunden!")
        else:
            # Wenn der Key als Text in der Variable steht (Cloud Deployment)
            cred_info = json.loads(key_json)
            cred = credentials.Certificate(cred_info)

        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        
        _db_client = firestore.client()
    
    return _db_client

def save_alert_url(url, category):
    try:
        db = get_db()
        
        # URL bereinigen für die Dokumenten-ID
        doc_id = url.replace("https://", "").replace("http://", "").replace("/", "-")
        # Firestore IDs dürfen nicht unendlich lang sein
        if len(doc_id) > 250:
            doc_id = doc_id[:250]

        doc_ref = db.collection("website").document(doc_id)
        
        # Speichern (merge=True aktualisiert nur, falls schon vorhanden)
        doc_ref.set({
            "url": url,
            "category": category,
            "alert": True,
            "processed": False, # Signal für den Summarizer
            "timestamp": firestore.SERVER_TIMESTAMP
        }, merge=True)
        
        logger.info(f"DB: Link gespeichert -> {url}")
        return True
    except Exception as e:
        logger.error(f"DB FEHLER beim Speichern von {url}: {e}")
        return False