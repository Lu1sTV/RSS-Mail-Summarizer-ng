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
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
CREDENTIALS_DIR = "credentials"
CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, "credentials.json")
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, "token.json")

# Secret names in Google Secret Manager
SECRET_CREDENTIALS = "credentials-credentials-json"
SECRET_TOKEN = "credentials-token-json"

def get_secret(secret_name):
    """Fetches a secret from Google Secret Manager (latest version)."""
    client = secretmanager.SecretManagerServiceClient()
    project_id = os.getenv("PROJECT_ID")
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")

def ensure_credentials_files():
    """
    Ensures credentials.json and token.json exist.
    - Local: uses local files in ./credentials
    - Cloud: writes them from Google Secret Manager to ./credentials
    """
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)

    # If running in Cloud (detected by env var), fetch from Secret Manager
    if os.getenv("K_SERVICE") or os.getenv("FUNCTION_TARGET"):  # Cloud Run / Cloud Functions
        if not os.path.exists(CREDENTIALS_FILE):
            creds_data = get_secret(SECRET_CREDENTIALS)
            with open(CREDENTIALS_FILE, "w") as f:
                f.write(creds_data)

        if not os.path.exists(TOKEN_FILE):
            token_data = get_secret(SECRET_TOKEN)
            with open(TOKEN_FILE, "w") as f:
                f.write(token_data)

    else:
        # Local mode: check that files exist
        if not os.path.exists(CREDENTIALS_FILE):
            raise FileNotFoundError(f"{CREDENTIALS_FILE} fehlt. Bitte lokal erstellen.")
        if not os.path.exists(TOKEN_FILE):
            print(f"Warnung: {TOKEN_FILE} fehlt – es wird beim ersten Login erstellt.")


def get_gmail_service():
    """Erstellt den Gmail API Service."""
    ensure_credentials_files()

    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

        # Token speichern
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

# Wichtig:
# labels in gmail müssen mit den Einträgen in dieser Map 1 zu 1 übereinstimmen.
# es muss ein filter in gmail erstellt werden, der alle eingehenden alert mails zum jeweiligen label hinzufügt
alert_map = {
    "Carlo Masala": ("alerts-carlo-masala", "alerts-carlo-masala-processed"),
}

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


def filter_links(links):
    """
    Filtert Links heraus, die unerwünschte Muster enthalten.
    Nur Links, die NICHT auf die Blacklist passen, werden zurückgegeben.
    """
    blacklist_patterns = [
        r"alerts/feedback",
        r"alerts/remove",
        r"alerts/edit",
        r"alerts\?s"
    ]

    filtered = []
    for link in links:
        if not any(re.search(pattern, link) for pattern in blacklist_patterns):
            filtered.append(link)

    return filtered

def get_label_id(service, label_name):
    """Holt die Gmail Label-ID anhand des Label-Namens"""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label["name"] == label_name:
            return label["id"]
    return None



def list_google_alerts():
    """
    Ruft alle Mails für alle Alerts in alert_map ab, extrahiert URLs aus HTML,
    markiert sie als 'processed' und gibt eine Map mit allen URLs pro Alert zurück.
    """
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
            results = service.users().messages().list(
                userId="me",
                labelIds=[label_id]
            ).execute()

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
                        "removeLabelIds": [label_id]
                    }
                ).execute()
                print(f"[{alias}] → Label geändert ({label_name} → {processed_label_name})")

            # Duplikate entfernen
            all_urls[alias] = list(set(found_urls))
            print(f"[{alias}] Gesamt {len(all_urls[alias])} eindeutige Links extrahiert.\n")

        return all_urls

    except HttpError as error:
        print(f"Ein Fehler ist aufgetreten: {error}")
        return {}




# all_urls = list_google_alerts()



