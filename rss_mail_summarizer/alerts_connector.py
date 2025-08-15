import os
import base64
import logging
from typing import List, Dict, Optional, Tuple

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

# ======= Konfiguration =======
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

# Pfad-Handling: Lokal standardmäßig ./credentials,
# in Cloud Run später per Env-Var CREDENTIALS_PATH=/secrets setzen.
BASE_CREDENTIALS_PATH = os.getenv("CREDENTIALS_PATH", "credentials")
CREDENTIALS_FILE = os.path.join(BASE_CREDENTIALS_PATH, "credentials.json")
TOKEN_FILE = os.path.join(BASE_CREDENTIALS_PATH, "token.json")

# Standard-Query (kann via Env-Var GMAIL_QUERY überschrieben werden)
DEFAULT_QUERY = os.getenv("GMAIL_QUERY", "label:alerts newer_than:7d")

# Logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("alerts_connector")


# ======= Auth / Service =======
def _ensure_paths() -> None:
    """Stellt sicher, dass der Basispfad existiert (nur lokal relevant)."""
    if not os.path.isdir(BASE_CREDENTIALS_PATH):
        os.makedirs(BASE_CREDENTIALS_PATH, exist_ok=True)


def _load_credentials() -> Credentials:
    """
    Lädt vorhandene Credentials (token.json), refresht sie bei Bedarf,
    oder startet lokal einmalig den interaktiven OAuth-Flow (Installed App).
    In Cloud-Umgebung wird vorausgesetzt, dass token.json und credentials.json
    bereits als Secrets gemountet sind (kein interaktiver Flow dort!).
    """
    creds: Optional[Credentials] = None

    # 1) Versuche token.json zu laden
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    # 2) Falls keine gültigen Credentials, versuche Refresh oder interaktiven Flow (nur lokal)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Access Token abgelaufen – refreshe mit Refresh Token.")
            creds.refresh(Request())
        else:
            # Hinweis: Dieser Flow öffnet einen Browser. In Cloud Run nicht nutzbar.
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"credentials.json nicht gefunden unter {CREDENTIALS_FILE}. "
                    f"Lege die OAuth-Clientdatei dort ab oder setze CREDENTIALS_PATH."
                )
            logger.info("Starte lokalen OAuth-Flow (InstalledAppFlow).")
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            # run_local_server öffnet einen Browser & startet einen lokalen Callback-Server
            creds = flow.run_local_server(port=0)

        # 3) Speichere (ggf. erneuerte) Credentials in token.json
        with open(TOKEN_FILE, "w", encoding="utf-8") as token:
            token.write(creds.to_json())
            logger.info("token.json aktualisiert.")

    return creds


def init_gmail_service():
    """
    Initialisiert den Gmail API Client.
    Lokal: erzeugt bei erstem Lauf token.json interaktiv.
    Cloud: erwartet, dass token.json & credentials.json via Secrets bereitstehen.
    """
    _ensure_paths()
    creds = _load_credentials()
    try:
        service = build("gmail", "v1", credentials=creds)
        return service
    except HttpError as e:
        logger.exception("Fehler beim Initialisieren des Gmail-Service: %s", e)
        raise


# ======= Gmail-Funktionen (Abruf) =======
def list_message_ids(
    service, query: str, max_results: int = 100
) -> List[str]:
    """
    Listet Message-IDs passend zur Gmail-Query.
    Handhabt Paginierung bis max_results.
    """
    user_id = "me"
    msg_ids: List[str] = []
    page_token: Optional[str] = None

    while True:
        resp = (
            service.users()
            .messages()
            .list(userId=user_id, q=query, maxResults=min(100, max_results - len(msg_ids)), pageToken=page_token)
            .execute()
        )
        ids = [m["id"] for m in resp.get("messages", [])]
        msg_ids.extend(ids)

        page_token = resp.get("nextPageToken")
        if not page_token or len(msg_ids) >= max_results:
            break

    return msg_ids


def get_message_metadata(
    service, message_id: str
) -> Dict[str, Optional[str]]:
    """
    Holt Header/Metadaten + Snippet einer Mail (ohne Parsing des HTML).
    Gibt Betreff, From, Date, internalDate zurück.
    """
    user_id = "me"
    msg = service.users().messages().get(userId=user_id, id=message_id, format="full").execute()

    headers = msg.get("payload", {}).get("headers", [])
    h = {hdr["name"].lower(): hdr["value"] for hdr in headers}

    meta = {
        "id": message_id,
        "threadId": msg.get("threadId"),
        "subject": h.get("subject"),
        "from": h.get("from"),
        "date": h.get("date"),
        "labelIds": ",".join(msg.get("labelIds", [])),
        "internalDate": msg.get("internalDate"),  # epoch ms
        "snippet": msg.get("snippet"),
        "sizeEstimate": msg.get("sizeEstimate"),
    }
    return meta


def _walk_parts(part: Dict) -> List[Dict]:
    """Flacht die MIME-Struktur in eine Liste aller Parts ab."""
    parts = []
    stack = [part]
    while stack:
        p = stack.pop()
        parts.append(p)
        for child in p.get("parts", []) or []:
            stack.append(child)
    return parts


def get_message_bodies(
    service, message_id: str
) -> Tuple[Optional[str], Optional[str]]:
    """
    Holt die Body-Inhalte (text/plain und text/html) einer Mail.
    Parsing/Extraktion der Artikel machen wir später.
    """
    user_id = "me"
    msg = service.users().messages().get(userId=user_id, id=message_id, format="full").execute()
    payload = msg.get("payload", {})

    text_plain = None
    text_html = None

    for p in _walk_parts(payload):
        mime = p.get("mimeType", "")
        body = p.get("body", {})
        data = body.get("data")
        if not data:
            continue

        decoded = base64.urlsafe_b64decode(data.encode("utf-8")).decode("utf-8", errors="replace")

        if mime == "text/plain" and text_plain is None:
            text_plain = decoded
        elif mime == "text/html" and text_html is None:
            text_html = decoded

    # Falls die Mail "einfache" Struktur ohne parts hat
    if not (text_plain or text_html):
        body = payload.get("body", {}).get("data")
        if body:
            decoded = base64.urlsafe_b64decode(body.encode("utf-8")).decode("utf-8", errors="replace")
            mime = payload.get("mimeType", "")
            if mime == "text/html":
                text_html = decoded
            else:
                text_plain = decoded

    return text_plain, text_html


# ======= CLI / Demo-Lauf =======
def main():
    """
    Minimaler End-to-End-Lauf:
    - Gmail-Service initialisieren (erstellt bei Bedarf token.json)
    - Message-IDs zur Query holen
    - Für die ersten N Mails Metadaten + (optional) Body holen
    - Nur ausgeben – KEIN Parsing der Artikel (kommt später)
    """
    query = DEFAULT_QUERY
    logger.info("Nutze Query: %s", query)

    service = init_gmail_service()

    msg_ids = list_message_ids(service, query=query, max_results=int(os.getenv("MAX_RESULTS", "20")))
    if not msg_ids:
        logger.info("Keine Mails gefunden.")
        return

    logger.info("Gefundene Mails: %d", len(msg_ids))

    for i, mid in enumerate(msg_ids, start=1):
        meta = get_message_metadata(service, mid)
        logger.info("[%d] %s | From: %s | Date: %s | internalDate: %s",
                    i, meta["subject"], meta["from"], meta["date"], meta["internalDate"])

        if os.getenv("FETCH_BODIES", "0") == "1":
            text_plain, text_html = get_message_bodies(service, mid)
            # Hier nur Länge ausgeben, Parsing kommt später
            logger.info("  Body text/plain: %s chars | text/html: %s chars",
                        len(text_plain) if text_plain else 0,
                        len(text_html) if text_html else 0)


if __name__ == "__main__":
    main()
