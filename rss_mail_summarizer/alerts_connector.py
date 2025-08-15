import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
import base64
from bs4 import BeautifulSoup
from googleapiclient.errors import HttpError

"""
Lokaler Start:
1. credentials/credentials.json aus Google Cloud Console herunterladen.
2. Skript starten → Browser-Login durchführen.
3. credentials/token.json wird erstellt → ab dann Login ohne Browser.

Cloud Run:
1. credentials.json + token.json in Google Secret Manager ablegen.
2. Secrets beim Start in Cloud Run in den Ordner /app/credentials mounten.
3. Skript funktioniert ohne Änderungen.
"""

# --- Konfiguration ---
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
CREDENTIALS_DIR = "credentials"
CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, "credentials.json")
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, "token.json")

def get_gmail_service():
    """
    Erstellt den Gmail API Service.
    Nutzt immer Dateien aus dem credentials/ Ordner.
    """
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(f"{CREDENTIALS_FILE} fehlt. Bitte erstellen oder in Cloud Secrets ablegen.")

        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

        # Token speichern
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

# def list_google_alerts():
#     """
#     Ruft Google Alerts E-Mails ab und gibt Snippets aus.
#     """
#     service = get_gmail_service()
#     results = service.users().messages().list(
#         userId="me",
#         q="from:googlealerts-noreply@google.com"
#     ).execute()
#
#     messages = results.get("messages", [])
#     print(f"{len(messages)} Nachrichten gefunden.")
#
#     for m in messages:
#         msg = service.users().messages().get(userId="me", id=m["id"]).execute()
#         print(f"- {msg['snippet']}")




def get_label_id(service, label_name):
    """Holt die Gmail Label-ID anhand des Label-Namens"""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label["name"] == label_name:
            return label["id"]
    return None

def list_google_alerts():
    """
    Ruft alle Mails mit dem Label 'alerts' ab, extrahiert URLs aus HTML,
    markiert sie als 'alerts-processed' und gibt eine Liste aller URLs zurück.
    """
    service = get_gmail_service()
    found_urls = []

    try:
        # Label-IDs abrufen
        alerts_label_id = get_label_id(service, "alerts")
        processed_label_id = get_label_id(service, "alerts-processed")
        if not alerts_label_id or not processed_label_id:
            raise ValueError("Label 'alerts' oder 'alerts-processed' existiert nicht.")

        # Mails mit Label 'alerts' abrufen
        results = service.users().messages().list(
            userId="me",
            labelIds=[alerts_label_id]
        ).execute()

        messages = results.get("messages", [])

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
            for a_tag in soup.find_all("a", href=True):
                found_urls.append(a_tag["href"])

            # Mail als 'alerts-processed' markieren
            service.users().messages().modify(
                userId="me",
                id=m["id"],
                body={
                    "addLabelIds": [processed_label_id],
                    "removeLabelIds": [alerts_label_id]
                }
            ).execute()

        # Duplikate entfernen
        return list(set(found_urls))

    except HttpError as error:
        print(f"Ein Fehler ist aufgetreten: {error}")
        return []



urls = list_google_alerts()
for url in urls:
    print(url)


