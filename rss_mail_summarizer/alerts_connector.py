"""
Dieses Modul verbindet sich mit der Gmail API, um automatisch Google Alerts E-Mails
auszulesen. Die enthaltenen Links werden extrahiert und irrelevante Links werden gefiltert.
Anschließend werden die übrigen Links in der Firestore-Datenbank gespeichert.
"""

# package imports
import os
import logging
import base64
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from bs4 import BeautifulSoup
from googleapiclient.errors import HttpError
from google.cloud import secretmanager

# Imports eigener Funktionen
from database import add_alert_to_website_collection
from utils.logger import logger

# Google API Scopes und Dateipfade für Credentials
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

CREDENTIALS_DIR = "credentials"
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
    logger.debug("Hole Secret '%s' aus Projekt '%s'", secret_name, project_id)
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("utf-8")


# Stellt sicher, dass die Credentials-Dateien vorhanden sind, sonst aus Secret Manager holen
def ensure_credentials():
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)
    project_id = os.environ["PROJECT_ID"]

    if not os.path.exists(CREDENTIALS_FILE):
        logger.warning("credentials.json nicht gefunden – hole aus Secret Manager")
        creds_data = get_secret(SECRET_CREDENTIALS, project_id)
        with open(CREDENTIALS_FILE, "w") as f:
            f.write(creds_data)
        logger.info("credentials.json erfolgreich angelegt")

    if not os.path.exists(TOKEN_FILE):
        logger.warning("token.json nicht gefunden – hole aus Secret Manager")
        token_data = get_secret(SECRET_TOKEN, project_id)
        with open(TOKEN_FILE, "w") as f:
            f.write(token_data)
        logger.info("token.json erfolgreich angelegt")


# Erstellt und gibt einen Gmail API Service zurück
def get_gmail_service():
    ensure_credentials()

    creds = None
    if os.path.exists(TOKEN_FILE):
        logger.debug("Lade Credentials aus token.json")
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            logger.error("%s fehlt. Bitte Datei bereitstellen oder in Cloud Secrets ablegen.", CREDENTIALS_FILE)
            raise FileNotFoundError(
                f"{CREDENTIALS_FILE} fehlt. Bitte erstellen oder in Cloud Secrets ablegen."
            )
        logger.info("Starte OAuth-Flow für Gmail API")
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        logger.info("Neues token.json erstellt")

    logger.info("Gmail Service erfolgreich initialisiert")
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
    filtered = [link for link in links if not any(b in link for b in blacklist)]
    logger.debug("Links gefiltert: %d → %d", len(links), len(filtered))
    return filtered


# Holt die Gmail Label-ID anhand des Label-Namens
def get_label_id(service, label_name):
    """Holt die Gmail Label-ID anhand des Label-Namens"""
    labels = service.users().labels().list(userId="me").execute().get("labels", [])
    for label in labels:
        if label["name"] == label_name:
            logger.debug("Label-ID für '%s' gefunden: %s", label_name, label["id"])
            return label["id"]
    logger.warning("Label '%s' nicht gefunden", label_name)
    return None


"""
Ruft alle Mails für alle Alerts in alert_map ab, extrahiert URLs aus HTML,
markiert sie als 'processed' und gibt eine Map mit allen URLs pro Alert zurück.
"""
def list_google_alerts():
    logger.info("Starte Abfrage der Google Alerts")

    service = get_gmail_service()
    all_urls = {}

    try:
        for alias, (label_name, processed_label_name) in alert_map.items():
            found_urls = []
            logger.info("Verarbeite Alert '%s'", alias)

            # Label-IDs abrufen
            label_id = get_label_id(service, label_name)
            processed_label_id = get_label_id(service, processed_label_name)
            if not label_id or not processed_label_id:
                logger.warning(
                    "Labels '%s' oder '%s' existieren nicht – überspringe %s",
                    label_name,
                    processed_label_name,
                    alias,
                )
                continue

            # Mails mit Label abrufen
            results = (
                service.users()
                .messages()
                .list(userId="me", labelIds=[label_id])
                .execute()
            )

            messages = results.get("messages", [])
            logger.info("[%s] %d Nachrichten gefunden", alias, len(messages))

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
                logger.debug("[%s] %d Links extrahiert", alias, len(links_in_mail))

                # Blacklist filtern
                links_in_mail = filter_links(links_in_mail)

                # URLs in DB speichern
                for url in links_in_mail:
                    add_alert_to_website_collection(url, category=alias)
                    logger.debug("[%s] URL gespeichert: %s", alias, url)

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
                logger.debug("[%s] Label geändert (%s → %s)", alias, label_name, processed_label_name)

            # Duplikate entfernen
            all_urls[alias] = list(set(found_urls))
            logger.info("[%s] Gesamt %d eindeutige Links extrahiert", alias, len(all_urls[alias]))

        return all_urls

    except HttpError as error:
        logger.error("Ein Fehler ist aufgetreten: %s", error, exc_info=True)
        return {}


if __name__ == "__main__":
    list_google_alerts()
