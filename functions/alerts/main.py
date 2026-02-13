import os
import base64
import logging
import functions_framework
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from bs4 import BeautifulSoup
from urllib.parse import unquote

from alerts_database import save_alert_url
from alerts_config import ALERT_CONFIG, LINK_BLACKLIST

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def get_gmail_service():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(base_dir, 'keys', 'token.json')

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
        return build('gmail', 'v1', credentials=creds)
    else:
        raise Exception(f"FEHLER: {token_path} fehlt! Bitte 'python keys/generate_token.py' ausführen.")

def get_label_id(service, label_name):
    results = service.users().labels().list(userId='me').execute()
    labels = results.get('labels', [])
    for l in labels:
        if l['name'] == label_name:
            return l['id']
    return None

def is_blacklisted(url):
    url_lower = url.lower()
    for bad_word in LINK_BLACKLIST:
        if bad_word.lower() in url_lower:
            return True
    return False

def process_single_alert(service, config):
    label_in = config["label"]
    label_out = config["processed_label"]
    category = config["name"]

    logger.info(f"--- Prüfe '{category}' ({label_in}) ---")

    id_in = get_label_id(service, label_in)
    id_out = get_label_id(service, label_out)

    if not id_in:
        logger.warning(f"Label '{label_in}' nicht gefunden.")
        return 0
    if not id_out:
        logger.warning(f"Ziel-Label '{label_out}' nicht gefunden. Bitte in Gmail anlegen!")
        return 0

    results = service.users().messages().list(userId='me', labelIds=[id_in]).execute()
    messages = results.get('messages', [])

    if not messages:
        logger.info(f"Keine neuen Nachrichten.")
        return 0

    count_processed = 0

    for msg_summary in messages:
        try:
            msg_id = msg_summary['id']
            msg = service.users().messages().get(userId='me', id=msg_id).execute()

            payload = msg['payload']
            body_data = ""

            if 'parts' in payload:
                for part in payload['parts']:
                    if part['mimeType'] == 'text/html':
                        body_data = part['body']['data']
            elif payload.get('mimeType') == 'text/html':
                body_data = payload['body']['data']

            if not body_data:
                logger.info(f"Mail {msg_id} übersprungen: Kein HTML-Inhalt.")
                continue

            html = base64.urlsafe_b64decode(body_data).decode()
            soup = BeautifulSoup(html, 'html.parser')

            links_saved = 0
            for a in soup.find_all('a', href=True):
                href = a['href']
                final_url = href

                if "google.com/url" in href:
                    try:
                        if "q=" in href:
                            raw_url = href.split("q=")[1].split("&")[0]
                            final_url = unquote(raw_url)
                        elif "url=" in href:
                            raw_url = href.split("url=")[1].split("&")[0]
                            final_url = unquote(raw_url)
                    except:
                        pass

                if not is_blacklisted(final_url):
                    if save_alert_url(final_url, category):
                        links_saved += 1

            if links_saved > 0:
                logger.info(f"Mail {msg_id}: {links_saved} Links gespeichert.")
            else:
                logger.info(f"Mail {msg_id}: Keine relevanten Links gefunden.")

            service.users().messages().modify(
                userId='me',
                id=msg_id,
                body={
                    'addLabelIds': [id_out],
                    'removeLabelIds': [id_in]
                }
            ).execute()
            count_processed += 1

        except Exception as e:
            logger.error(f"Fehler bei Mail {msg_summary['id']}: {e}")

    return count_processed

@functions_framework.http
def alerts_mvp_endpoint(request):
    """Entry Point für die Cloud Function."""
    try:
        service = get_gmail_service()
        total_mails = 0

        for config in ALERT_CONFIG:
            total_mails += process_single_alert(service, config)

        return f"Erfolg: {total_mails} Mails verarbeitet und verschoben.", 200

    except Exception as e:
        logger.critical(f"Server Error: {e}")
        return f"Error: {e}", 500