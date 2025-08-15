import os
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

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

def list_google_alerts():
    """
    Ruft Google Alerts E-Mails ab und gibt Snippets aus.
    """
    service = get_gmail_service()
    results = service.users().messages().list(
        userId="me",
        q="from:googlealerts-noreply@google.com"
    ).execute()

    messages = results.get("messages", [])
    print(f"{len(messages)} Nachrichten gefunden.")

    for m in messages:
        msg = service.users().messages().get(userId="me", id=m["id"]).execute()
        print(f"- {msg['snippet']}")


list_google_alerts()


