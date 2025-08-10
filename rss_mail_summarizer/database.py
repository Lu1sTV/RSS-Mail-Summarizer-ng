from datetime import datetime
import os
import json
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from sentence_transformers import SentenceTransformer

# -- embedding model --
model = SentenceTransformer('all-MiniLM-L6-v2')

# Service Account Schlüssel laden 
# Unterscheidung für lokale Ausführung und über Cloud Console
def initialize_firebase():
    service_account_key = os.environ.get("_MY_SECRET")

    if service_account_key:
        print("Initializing Firebase with secret from environment variable _MY_SECRET")
        # The secret is expected as JSON string, so parse it
        service_account_info = json.loads(service_account_key)
        cred = credentials.Certificate(service_account_info)
    else:
        print("Initializing Firebase with local serviceAccountKey.json file")
        cred = credentials.Certificate("serviceAccountKey.json")

    initialize_app(cred)

initialize_firebase()

# Firestore-Client erstellen
db = firestore.client()

#als document ID in der website collection in der Firebase
#wird die url verwendet. Bei dieser müssen jedoch die '/' entfernt/ersetzt werden:
def safe_url(url):
    safe_url = url.replace("/", "-")
    return safe_url


def add_datarecord(url, category, summary, reading_time, subcategory=None, mail_sent=False):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    vector_embedding = model.encode(summary).tolist()

    db.collection("website").document(safe_url(url)).update({
        "category": category,
        "summary": summary,
        "subcategory": subcategory,
        "mail_sent": mail_sent,
        "vector_embedding": vector_embedding,
        "processed": True,
        "timestamp": timestamp,
        "reading_time": reading_time
    })

    print(f"Datensatz aktualisiert: {url}")



def is_duplicate_url(url):
    doc = db.collection("website").document(safe_url(url)).get()
    return doc.exists


def get_unsent_entries():
    websites = db.collection('website').stream()

    entries = []

    for w in websites:
        if w.get('mail_sent') == False:
            url = w.get('url')
            category = w.get('category')
            summary = w.get('summary')
            subcategory = w.get('subcategory')
            reading_time = w.get('reading_time')

            entries.append((url, category, summary, subcategory, reading_time))
    
    # entries is a list of tuples with the following information: (url, category, summary, subcategory)
    return entries



def mark_as_sent(entries):
    # entries = [] 

    for entry in entries:
        url = entry[0]
        db.collection('website').document(safe_url(url)).update({'mail_sent': True})

    print("Entries marked as sent.")


################################################################

# erstellt neue, unverarbeitete einträge in der datenbank
def add_url_to_website_collection(url):
    doc_ref = db.collection("website").document(safe_url(url))
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.set({
            "url": url,
            "processed": False,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        })
        print(f"Neue URL gespeichert: {url}")
    else:
        print(f"URL bereits vorhanden (wird ignoriert): {url}")


# holt nur unverarbeitete einträge aus der datenbank
def get_unprocessed_urls():
    docs = db.collection("website").where("processed", "==", False).stream()
    return [doc.to_dict()["url"] for doc in docs]
