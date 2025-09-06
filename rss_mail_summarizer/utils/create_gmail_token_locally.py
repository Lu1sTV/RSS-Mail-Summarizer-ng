""" Dieses Skript wird einmalig lokal ausgeführt, um ein Gmail OAuth-Token zu erstellen.
Es öffnet den OAuth-Flow über den Browser, authentifiziert den Nutzer und speichert
die Zugangsdaten in der Datei /credentials/token.json.
Dieses Token wird später benötigt, um auf die Gmail API zuzugreifen. """

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

flow = InstalledAppFlow.from_client_secrets_file(
    "../credentials/credentials.json", SCOPES
)
creds = flow.run_local_server(port=0)

with open("../credentials/token.json", "w") as token:
    token.write(creds.to_json())

print("Token erfolgreich gespeichert.")