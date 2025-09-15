"""
Dieses Modul verbindet sich mit der Gmail API, um automatisch Google Alerts E-Mails
auszulesen. Die enthaltenen Links werden extrahiert und irrelevante Links werden gefiltert.
Anschließend werden die übrigen Links in der Firestore-Datenbank gespeichert.
"""

# package imports
import os
import json
import base64
from dotenv import load_dotenv
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from bs4 import BeautifulSoup
from googleapiclient.errors import HttpError

# Importe eigener Funktionen
from utils.logger import logger

load_dotenv()

# Google API Scopes
SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

# Lokale Pfade
CREDENTIALS_DIR = "credentials"
CREDENTIALS_FILE = os.path.join(CREDENTIALS_DIR, "credentials.json")
TOKEN_FILE = os.path.join(CREDENTIALS_DIR, "token.json")

# Map von Alert-Namen zu Gmail-Labeln
alert_map = {
    "Carlo Masala": ("alerts-carlo-masala", "alerts-carlo-masala-processed"),
}


# Holt Secret aus Umgebungsvariable (von Cloudbuild.yaml gesetzt), 
# sonst aus lokaler Datei.
def get_local_secret(env_var_name: str, local_path: str):
    if env_var_name in os.environ:
        logger.info(f"{env_var_name} wird aus Umgebungsvariable geladen.")
        try:
            return json.loads(os.environ[env_var_name])
        except Exception as e:
            logger.error(f"Fehler beim Laden von {env_var_name} aus Umgebungsvariable: {e}")
            raise
    elif os.path.exists(local_path):
        logger.info(f"{env_var_name} wird aus lokaler Datei {local_path} geladen.")
        with open(local_path, "r") as f:
            return json.load(f)
    else:
        logger.error(f"{env_var_name} nicht gefunden – weder Umgebungsvariable noch lokale Datei {local_path}.")
        raise FileNotFoundError(f"{env_var_name} nicht verfügbar.")


def ensure_credentials():
    os.makedirs(CREDENTIALS_DIR, exist_ok=True)

    # credentials.json laden oder aus ENV schreiben
    if not os.path.exists(CREDENTIALS_FILE) and "CREDENTIALS_CREDENTIALS_JSON" in os.environ:
        logger.info("credentials.json nicht gefunden – schreibe aus ENV.")
        creds_json = os.environ["CREDENTIALS_CREDENTIALS_JSON"]
        with open(CREDENTIALS_FILE, "w") as f:
            f.write(creds_json)
        logger.info("credentials.json erfolgreich erstellt aus ENV.")

    # token.json ggf. aus ENV schreiben (nur wenn du Token vorher gespeichert hast)
    if not os.path.exists(TOKEN_FILE) and "CREDENTIALS_TOKEN_JSON" in os.environ:
        logger.info("token.json nicht gefunden – schreibe aus ENV.")
        token_json = os.environ["CREDENTIALS_TOKEN_JSON"]
        with open(TOKEN_FILE, "w") as f:
            f.write(token_json)
        logger.info("token.json erfolgreich erstellt aus ENV.")


def get_gmail_service():
    ensure_credentials()

    creds = None
    if os.path.exists(TOKEN_FILE):
        logger.debug("Lade Credentials aus token.json")
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    else:
        if not os.path.exists(CREDENTIALS_FILE):
            logger.error(f"{CREDENTIALS_FILE} fehlt. Bitte bereitstellen oder in ENV ablegen.")
            raise FileNotFoundError(f"{CREDENTIALS_FILE} fehlt.")
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
