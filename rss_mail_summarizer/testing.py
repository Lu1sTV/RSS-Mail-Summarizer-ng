#package imports
import os
import json
from dotenv import load_dotenv
from google.cloud import secretmanager
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from urllib.parse import urlparse, parse_qs, unquote
import re
from datetime import datetime
from google.cloud.firestore_v1.base_query import FieldFilter

load_dotenv()
SERVICE_ACCOUNT_KEY_PATH = "rss_mail_summarizer/serviceAccountKey.json"


# Google Secret einholen wenn in Google ausgeführt
def access_secret(secret_id: str, project_id: str):
    """Fetch secret from Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")


# Initialisiert Firebase mit Service Account Key (lokal oder aus Secret Manager)
def initialize_firebase():
    project_id = os.environ["PROJECT_ID"]
    secret_id = "rss-firebase-key"

    try:
        # Wenn in Google:
        service_account_key = access_secret(secret_id, project_id)
        print("Initializing Firebase with secret from Secret Manager")
        service_account_info = json.loads(service_account_key)
        cred = credentials.Certificate(service_account_info)
    except Exception as e:
        # Wenn lokale Ausführung:
        print(f"Falling back to local serviceAccountKey.json file. Reason: {e}")
        cred = credentials.Certificate(SERVICE_ACCOUNT_KEY_PATH)

    if not firebase_admin._apps:
        initialize_app(cred)


initialize_firebase()

# Firestore-Client wird erstellt
db = firestore.client()

def delete_unprocessed_websites(batch_size: int = 100):
    """
    Deletes all documents from the 'website' collection where processed == False.
    Deletes in batches (default: 100) to avoid timeouts.
    """
    while True:
        # Query unprocessed docs
        docs = (
            db.collection("website")
            .where("processed", "==", False)
            .limit(batch_size)
            .stream()
        )

        docs = list(docs)
        if not docs:
            print("Keine unprocessed-Docs mehr gefunden.")
            break

        # Batch delete
        batch = db.batch()
        for doc in docs:
            batch.delete(doc.reference)
        batch.commit()

        print(f"{len(docs)} unprocessed-Docs gelöscht...")

if __name__ == "__main__":
    delete_unprocessed_websites()


