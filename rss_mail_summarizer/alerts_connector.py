"""Dieses Modul verbindet sich mit der Gmail API, um automatisch Google Alerts E-Mails
auszulesen. Die enthaltenen Links werden extrahiert, in der Firestore-Datenbank
gespeichert und die E-Mails danach als "processed" markiert.
Damit werden Alerts nur einmal verarbeitet."""

import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import base64
from bs4 import BeautifulSoup
from googleapiclient.errors import HttpError
import re
from google.cloud import secretmanager
from database import add_alert_to_website_collection
import json

# Google API Scopes und Dateipfade für Credentials
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

CREDENTIALS_DIR = "rss_mail_summarizer/credentials"
CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, "credentials.json")
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, "token.json")

SECRET_CREDENTIALS = "credentials-credentials-json"
SECRET_TOKEN = "credentials-token-json"

# Map von Alert-Namen zu Gmail-Labeln
alert_map = {
    "Carlo Masala": ("alerts-carlo-masala", "alerts-carlo-masala-processed"),
}


# Holt ein Secret aus dem Google Secret Manager
def get_secret(secret_name, project_id):
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


# Stellt sicher, dass die Credentials-Dateien vorhanden sind, sonst aus Secret Manager holen
def ensure_credentials():
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    project_id = os.environ["PROJECT_ID"]

    if not os.path.exists(CREDENTIALS_FILE):
        print("credentials.json not found. Fetching from Secret Manager...")
        creds_data = get_secret(SECRET_CREDENTIALS, project_id)
        with open(CREDENTIALS_FILE, "w") as f:
            f.write(creds_data)

    if not os.path.exists(TOKEN_FILE):
        print("token.json not found. Fetching from Secret Manager...")
        token_data = get_secret(SECRET_TOKEN, project_id)
        with open(TOKEN_FILE, "w") as f:
            f.write(token_data)


# Erstellt und gibt einen Gmail API Service zurück
def get_gmail_service():
    ensure_credentials()

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(
                f"{CREDENTIALS_FILE} fehlt. Bitte erstellen oder in Cloud Secrets ablegen."
            )
        # OAuth-Flow starten
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


# Filtert unerwünschte Links heraus
def filter_links(links):
    blacklist = [
        "alerts/feedback",
        "alerts/remove",
        "alerts/edit",
        "alerts",
        "alerts/share"
    ]
    return [link for link in links if not any(b in link for b in blacklist)]




# Holt die Gmail Label-ID anhand des Label-Namens
def get_label_id(service, label_name):
    """Holt die Gmail Label-ID anhand des Label-Namens"""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label["name"] == label_name:
            return label["id"]
    return None


""" Ruft alle Mails für alle Alerts in alert_map ab, extrahiert URLs aus HTML,
markiert sie als 'processed' und gibt eine Map mit allen URLs pro Alert zurück. """

def list_google_alerts():

    service = get_gmail_service()
    all_urls = {}

    try:
        for alias, (label_name, processed_label_name) in alert_map.items():
            found_urls = []

            # Label-IDs abrufen
            label_id = get_label_id(service, label_name)
            processed_label_id = get_label_id(service, processed_label_name)
            if not label_id or not processed_label_id:
                print(f"Label '{label_name}' oder '{processed_label_name}' existiert nicht. Überspringe {alias}.")
                continue

            # Mails mit Label abrufen
            results = (
                service.users()
                .messages()
                .list(userId="me", labelIds=[label_id])
                .execute()
            )

            messages = results.get("messages", [])
            print(f"[{alias}] {len(messages)} Nachrichten gefunden.")

            for m in messages:
                msg = service.users().messages().get(
                    userId="me",
                    id=m["id"],
                    format="full"
                ).execute()

                body_html = ""
                if "parts" in msg["payload"]:
                    for part in msg["payload"]["parts"]:
                        if part.get("mimeType") == "text/html":
                            data = part["body"].get("data")
                            if data:
                                body_html += base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")

                # URLs aus HTML href-Attributen extrahieren
                soup = BeautifulSoup(body_html, "html.parser")
                links_in_mail = [a_tag["href"] for a_tag in soup.find_all("a", href=True)]
                print(f"[{alias}] → {len(links_in_mail)} Links gefunden.")

                # Blacklist filtern
                links_in_mail = filter_links(links_in_mail)

                # URLs in DB speichern
                for url in links_in_mail:
                    add_alert_to_website_collection(url, category=alias)

                found_urls.extend(links_in_mail)

                # Mail als 'processed' markieren
                service.users().messages().modify(
                    userId="me",
                    id=m["id"],
                    body={
                        "addLabelIds": [processed_label_id],
                        "removeLabelIds": [label_id],
                    },
                ).execute()
                print(f"[{alias}] → Label geändert ({label_name} → {processed_label_name})")

            # Duplikate entfernen
            all_urls[alias] = list(set(found_urls))
            print(f"[{alias}] Gesamt {len(all_urls[alias])} eindeutige Links extrahiert.\n")

        return all_urls

    except HttpError as error:
        print(f"Ein Fehler ist aufgetreten: {error}")
        return {}


if __name__ == "__main__":
    list_google_alerts()


