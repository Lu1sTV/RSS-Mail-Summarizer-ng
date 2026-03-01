import os
import sys
import json
import base64
import logging
import traceback
from typing import List, Dict, Any, Optional, Tuple

import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError
from bs4 import BeautifulSoup
from urllib.parse import unquote

# Logger Setup
logger = logging.getLogger("alerts_processor")
logger.setLevel(logging.DEBUG)

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)

class Config:
    ALERT_CONFIG: List[Dict[str, str]] = [
        {"name": "Carlo Masala", "label": "alerts-carlo-masala", "processed_label": "alerts-carlo-masala-processed"}
    ]
    LINK_BLACKLIST: List[str] = [
        "google.com/alerts", "alerts/remove", "alerts/edit", "support.google.com", "google.com/settings"
    ]
    SCOPES: List[str] = ["https://www.googleapis.com/auth/gmail.modify"]

class FirestoreDatabase:
    def __init__(self) -> None:
        try:
            key_json: Optional[str] = os.environ.get("RSS_FIREBASE_KEY")
            if key_json:
                logger.debug("Nutze Firebase Secret aus Umgebungsvariable.")
                cred = credentials.Certificate(json.loads(key_json))
            else:
                logger.debug("Nutze lokales Firebase ServiceAccountKey.json.")
                key_path: str = os.path.join(os.path.dirname(__file__), "keys", "serviceAccountKey.json")
                cred = credentials.Certificate(key_path)

            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            self.db = firestore.client()
            
            # Aktiver Verbindungstest
            self.db.collection("website").limit(1).get()
            logger.info("Verbindung zu Firestore erfolgreich hergestellt.")
        except Exception as e:
            logger.error(f"Kritischer Fehler bei der Firestore-Verbindung: {e}")
            raise RuntimeError(f"Firestore Connection failed: {str(e)}")

    def save_url(self, url: str, category: str) -> None:
        try:
            doc_id: str = url.replace("https://", "").replace("http://", "").replace("/", "-")[:250]
            self.db.collection("website").document(doc_id).set({
                "url": url,
                "category": category,
                "alert": True,
                "processed": False,
                "timestamp": firestore.SERVER_TIMESTAMP
            }, merge=True)
            logger.debug(f"URL gespeichert: {url} (Kategorie: {category})")
        except Exception as e:
            logger.error(f"Fehler beim Speichern der URL {url} in Firestore: {e}")
            raise

class GmailService:
    def __init__(self) -> None:
        try:
            token_env: Optional[str] = os.environ.get("GMAIL_TOKEN_JSON")
            
            if token_env:
                logger.debug("Nutze Gmail Token aus Umgebungsvariable.")
                token_data: Dict[str, Any] = json.loads(token_env)
                creds: Credentials = Credentials.from_authorized_user_info(token_data, Config.SCOPES)
            else:
                logger.debug("Nutze lokales token.json.")
                token_path: str = os.path.join(os.path.dirname(__file__), 'keys', 'token.json')
                creds: Credentials = Credentials.from_authorized_user_file(token_path, Config.SCOPES)
                
            self.service: Resource = build('gmail', 'v1', credentials=creds)
            
            # Aktiver Verbindungstest und Auth-Check
            profile = self.service.users().getProfile(userId='me').execute()
            logger.info(f"Verbindung zu Gmail erfolgreich. Angemeldet als: {profile.get('emailAddress')}")
        except HttpError as e:
            logger.error(f"Gmail API HTTP Error während der Initialisierung: {e}")
            raise RuntimeError(f"Gmail Connection failed (HTTP Error): {e}")
        except Exception as e:
            logger.error(f"Kritischer Fehler bei der Gmail-Verbindung: {e}")
            raise RuntimeError(f"Gmail Connection failed: {str(e)}")

    def get_label_id(self, label_name: str) -> Optional[str]:
        try:
            response: Dict[str, Any] = self.service.users().labels().list(userId='me').execute()
            labels: List[Dict[str, str]] = response.get('labels', [])
            for label in labels:
                if label['name'].lower() == label_name.lower():
                    return label['id']
            return None
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Label-ID für '{label_name}': {e}")
            raise

    def get_messages(self, label_id: str) -> List[Dict[str, str]]:
        try:
            response: Dict[str, Any] = self.service.users().messages().list(userId='me', labelIds=[label_id]).execute()
            return response.get('messages', [])
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Nachrichten für Label-ID {label_id}: {e}")
            raise

    def get_message_body(self, msg_id: str) -> str:
        try:
            msg: Dict[str, Any] = self.service.users().messages().get(userId='me', id=msg_id).execute()
            payload: Dict[str, Any] = msg.get('payload', {})
            parts: List[Dict[str, Any]] = payload.get('parts', [payload])
            
            for part in parts:
                if part.get('mimeType') == 'text/html':
                    return part.get('body', {}).get('data', '')
            return ""
        except Exception as e:
            logger.error(f"Fehler beim Abrufen des Bodys für Nachricht {msg_id}: {e}")
            return ""

    def move_message(self, msg_id: str, id_in: str, id_out: str) -> None:
        try:
            self.service.users().messages().modify(
                userId='me', 
                id=msg_id, 
                body={'addLabelIds': [id_out], 'removeLabelIds': [id_in]}
            ).execute()
            logger.debug(f"Nachricht {msg_id} erfolgreich verschoben.")
        except Exception as e:
            logger.error(f"Fehler beim Verschieben der Nachricht {msg_id}: {e}")
            raise

class AlertProcessor:
    def __init__(self, gmail: GmailService, db: FirestoreDatabase) -> None:
        self.gmail: GmailService = gmail
        self.db: FirestoreDatabase = db

    def _clean_url(self, url: str) -> str:
        if "google.com/url" in url and ("q=" in url or "url=" in url):
            param: str = "q=" if "q=" in url else "url="
            try:
                return unquote(url.split(param)[1].split("&")[0])
            except IndexError:
                pass
        return url

    def _is_blacklisted(self, url: str) -> bool:
        return any(b.lower() in url.lower() for b in Config.LINK_BLACKLIST)

    def process_config(self, config: Dict[str, str]) -> Dict[str, Any]:
        result = {"name": config["name"], "processed": 0, "status": "ok", "error": None}
        logger.info(f"Starte Verarbeitung für Alert-Config: {config['name']}")

        try:
            id_in: Optional[str] = self.gmail.get_label_id(config["label"])
            id_out: Optional[str] = self.gmail.get_label_id(config["processed_label"])
            
            if not id_in:
                error_msg = f"Eingangs-Label '{config['label']}' nicht in Gmail gefunden! Bitte in Gmail prüfen."
                logger.warning(error_msg)
                result["status"] = "warning"
                result["error"] = error_msg
                return result
                
            if not id_out:
                error_msg = f"Ziel-Label '{config['processed_label']}' nicht in Gmail gefunden! Bitte in Gmail anlegen."
                logger.warning(error_msg)
                result["status"] = "warning"
                result["error"] = error_msg
                return result

            messages: List[Dict[str, str]] = self.gmail.get_messages(id_in)
            logger.info(f"{len(messages)} Nachrichten im Label '{config['label']}' gefunden.")

            for msg_summary in messages:
                msg_id: str = msg_summary['id']
                body_data: str = self.gmail.get_message_body(msg_id)
                
                if not body_data:
                    logger.warning(f"Kein HTML-Body für Nachricht {msg_id} gefunden. Überspringe.")
                    continue

                html_content: str = base64.urlsafe_b64decode(body_data).decode()
                soup: BeautifulSoup = BeautifulSoup(html_content, 'html.parser')
                
                links_found = 0
                for a in soup.find_all('a', href=True):
                    url: str = self._clean_url(a['href'])
                    if not self._is_blacklisted(url):
                        self.db.save_url(url, config["name"])
                        links_found += 1

                logger.debug(f"{links_found} gültige Links in Nachricht {msg_id} gefunden.")

                self.gmail.move_message(msg_id, id_in, id_out)
                result["processed"] += 1

            logger.info(f"Verarbeitung für '{config['name']}' abgeschlossen. {result['processed']} Mails verarbeitet.")
            return result

        except Exception as e:
            error_msg = f"Fehler bei der Verarbeitung von '{config['name']}': {str(e)}"
            logger.error(error_msg)
            result["status"] = "error"
            result["error"] = error_msg
            result["traceback"] = traceback.format_exc()
            return result

@functions_framework.http
def alerts_mvp_endpoint(request: Any) -> Tuple[str, int]:
    logger.info("Starte alerts_mvp_endpoint Ausführung.")
    try:
        gmail = GmailService()
        db = FirestoreDatabase()
        processor = AlertProcessor(gmail, db)
        
        results = []
        total_processed = 0
        has_errors = False
        
        for c in Config.ALERT_CONFIG:
            res = processor.process_config(c)
            results.append(res)
            total_processed += res["processed"]
            if res["status"] == "error":
                has_errors = True
                
        response_data = {
            "total_processed": total_processed,
            "details": results
        }
        
        if has_errors:
            logger.error("Ausführung mit Fehlern in einigen Configs beendet.")
            return json.dumps(response_data, indent=2), 500
            
        logger.info("Ausführung erfolgreich beendet.")
        return json.dumps(response_data, indent=2), 200

    except RuntimeError as re:
        logger.critical(f"Initialisierungsfehler: {re}")
        return json.dumps({"error": "Initialization failed", "details": str(re)}, indent=2), 500
    except Exception as e:
        logger.critical(f"Server Error: {e}\n{traceback.format_exc()}")
        return json.dumps({"error": "Internal Server Error", "details": str(e), "traceback": traceback.format_exc()}, indent=2), 500