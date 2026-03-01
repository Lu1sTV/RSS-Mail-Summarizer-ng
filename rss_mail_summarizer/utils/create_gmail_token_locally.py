"""Dieses Skript wird einmalig lokal ausgeführt, um ein Gmail OAuth-Token zu erstellen.
Es öffnet den OAuth-Flow über den Browser, authentifiziert den Nutzer und speichert
die Zugangsdaten in der Datei /credentials/token.json.
Dieses Token wird später benötigt, um auf die Gmail API zuzugreifen."""

# package imports
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow

#Imports eigener Funktionen
try:
    from .logger import logger
except ImportError:
    from logger import logger

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

BASE_DIR = Path(__file__).resolve().parents[1]
CREDENTIALS_FILE = BASE_DIR / "credentials" / "credentials.json"
TOKEN_FILE = BASE_DIR / "credentials" / "token.json"

def main():
    try:
        logger.debug("Starte Gmail OAuth-Flow...")

        # Starte den OAuth-Flow und speichere die Zugangsdaten
        flow = InstalledAppFlow.from_client_secrets_file(
            str(CREDENTIALS_FILE), SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

        logger.info("Token wurde erfolgreich gespeichert.")
    except FileNotFoundError as e:
        logger.error(f"Credentials-Datei nicht gefunden: {e}")
    except Exception as e:
        logger.error(f"Fehler beim Erstellen des Gmail OAuth-Tokens: {e}")


if __name__ == "__main__":
    main()