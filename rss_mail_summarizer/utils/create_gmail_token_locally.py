"""Dieses Skript wird einmalig lokal ausgeführt, um ein Gmail OAuth-Token zu erstellen.
Es öffnet den OAuth-Flow über den Browser, authentifiziert den Nutzer und speichert
die Zugangsdaten in der Datei /credentials/token.json.
Dieses Token wird später benötigt, um auf die Gmail API zuzugreifen."""

# package imports
from google_auth_oauthlib.flow import InstalledAppFlow

#Imports eigener Funktionen
from logger import logger

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

def main():
    try:
        logger.debug("Starte Gmail OAuth-Flow...")

        # Starte den OAuth-Flow und speichere die Zugangsdaten
        flow = InstalledAppFlow.from_client_secrets_file(
            "../credentials/credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)

        with open("../credentials/token.json", "w") as token:
            token.write(creds.to_json())

        logger.info("Token wurde erfolgreich gespeichert.")
    except FileNotFoundError as e:
        logger.error(f"Credentials-Datei nicht gefunden: {e}")
    except Exception as e:
        logger.error(f"Fehler beim Erstellen des Gmail OAuth-Tokens: {e}")


if __name__ == "__main__":
    main()