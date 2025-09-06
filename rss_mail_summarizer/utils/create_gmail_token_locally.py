from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]

flow = InstalledAppFlow.from_client_secrets_file(
    "../credentials/credentials.json", SCOPES
)
creds = flow.run_local_server(port=0)

# Token speichern
with open("../credentials/token.json", "w") as token:
    token.write(creds.to_json())

print("Token erfolgreich gespeichert.")