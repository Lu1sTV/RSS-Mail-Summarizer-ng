"""Dieses Skript wird einmalig lokal ausgeführt, um ein Gmail OAuth-Token zu erstellen.
Es öffnet den OAuth-Flow über den Browser, authentifiziert den Nutzer und speichert
die Zugangsdaten in der Datei /credentials/token.json.
Dieses Token wird später benötigt, um auf die Gmail API zuzugreifen."""

import os
import logging
from dotenv import load_dotenv
from google_auth_oauthlib.flow import InstalledAppFlow

# Load environment variables
load_dotenv()

# Get LOG_LEVEL from .env, default to INFO
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def main():
    try:
        logger.debug("Starting Gmail OAuth flow...")

        # Starte den OAuth-Flow und speichere die Zugangsdaten
        flow = InstalledAppFlow.from_client_secrets_file(
            "../credentials/credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open("../credentials/token.json", "w") as token:
            token.write(creds.to_json())

        logger.info("Token erfolgreich gespeichert.")
    except FileNotFoundError as e:
        logger.error(f"Credentials file not found: {e}")
    except Exception as e:
        logger.error(f"Fehler beim Erstellen des Gmail OAuth Tokens: {e}")


if __name__ == "__main__":
    main()