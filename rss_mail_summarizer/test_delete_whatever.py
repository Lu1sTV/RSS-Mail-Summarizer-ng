from datetime import datetime
import os
import json
from dotenv import load_dotenv
from google.cloud import secretmanager
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin

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

def delete_alerts_today():
    """Delete all documents from 'website' where alert=true and timestamp is today."""
    now = datetime.utcnow()
    start_of_day = datetime(year=now.year, month=now.month, day=now.day)

    # Query only on timestamp
    query = db.collection("website").where("timestamp", ">=", start_of_day)

    docs = query.stream()

    deleted_count = 0
    for doc in docs:
        data = doc.to_dict()
        if data.get("alert") is True:  # filter in Python
            print(f"Deleting doc {doc.id}: {data}")
            doc.reference.delete()
            deleted_count += 1

    print(f"Deleted {deleted_count} documents with alert=true from today.")


if __name__ == "__main__":
    delete_alerts_today()

