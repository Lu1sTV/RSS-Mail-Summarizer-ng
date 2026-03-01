import os
import json
import base64
import logging
from typing import List, Dict, Any, Optional, Tuple

import functions_framework
import firebase_admin
from firebase_admin import credentials, firestore
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from bs4 import BeautifulSoup
from urllib.parse import unquote

logging.basicConfig(level=logging.INFO)

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
        key_json: Optional[str] = os.environ.get("RSS_FIREBASE_KEY")
        if key_json:
            cred = credentials.Certificate(json.loads(key_json))
        else:
            key_path: str = os.path.join(os.path.dirname(__file__), "keys", "serviceAccountKey.json")
            cred = credentials.Certificate(key_path)

        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        self.db = firestore.client()

    def save_url(self, url: str, category: str) -> None:
        doc_id: str = url.replace("https://", "").replace("http://", "").replace("/", "-")[:250]
        self.db.collection("website").document(doc_id).set({
            "url": url,
            "category": category,
            "alert": True,
            "processed": False,
            "timestamp": firestore.SERVER_TIMESTAMP
        }, merge=True)


class GmailService:
    def __init__(self) -> None:
        token_path: str = os.path.join(os.path.dirname(__file__), 'keys', 'token.json')
        creds: Credentials = Credentials.from_authorized_user_file(token_path, Config.SCOPES)
        self.service: Resource = build('gmail', 'v1', credentials=creds)

    def get_label_id(self, label_name: str) -> Optional[str]:
        response: Dict[str, Any] = self.service.users().labels().list(userId='me').execute()
        labels: List[Dict[str, str]] = response.get('labels', [])
        return next((label['id'] for label in labels if label['name'] == label_name), None)

    def get_messages(self, label_id: str) -> List[Dict[str, str]]:
        response: Dict[str, Any] = self.service.users().messages().list(userId='me', labelIds=[label_id]).execute()
        return response.get('messages', [])

    def get_message_body(self, msg_id: str) -> str:
        msg: Dict[str, Any] = self.service.users().messages().get(userId='me', id=msg_id).execute()
        payload: Dict[str, Any] = msg.get('payload', {})
        parts: List[Dict[str, Any]] = payload.get('parts', [payload])
        
        for part in parts:
            if part.get('mimeType') == 'text/html':
                return part.get('body', {}).get('data', '')
        return ""

    def move_message(self, msg_id: str, id_in: str, id_out: str) -> None:
        self.service.users().messages().modify(
            userId='me', 
            id=msg_id, 
            body={'addLabelIds': [id_out], 'removeLabelIds': [id_in]}
        ).execute()


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

    def process_config(self, config: Dict[str, str]) -> int:
        id_in: Optional[str] = self.gmail.get_label_id(config["label"])
        id_out: Optional[str] = self.gmail.get_label_id(config["processed_label"])
        
        if not id_in or not id_out:
            return 0

        messages: List[Dict[str, str]] = self.gmail.get_messages(id_in)
        processed_count: int = 0

        for msg_summary in messages:
            msg_id: str = msg_summary['id']
            body_data: str = self.gmail.get_message_body(msg_id)
            
            if not body_data:
                continue

            html_content: str = base64.urlsafe_b64decode(body_data).decode()
            soup: BeautifulSoup = BeautifulSoup(html_content, 'html.parser')
            
            for a in soup.find_all('a', href=True):
                url: str = self._clean_url(a['href'])
                if not self._is_blacklisted(url):
                    self.db.save_url(url, config["name"])

            self.gmail.move_message(msg_id, id_in, id_out)
            processed_count += 1

        return processed_count


@functions_framework.http
def alerts_mvp_endpoint(request: Any) -> Tuple[str, int]:
    try:
        gmail = GmailService()
        db = FirestoreDatabase()
        processor = AlertProcessor(gmail, db)
        
        total_processed: int = sum(processor.process_config(c) for c in Config.ALERT_CONFIG)
        
        return f"{total_processed} Mails verarbeitet.", 200
    except Exception as e:
        logging.critical(f"Server Error: {e}")
        return f"Error: {e}", 500