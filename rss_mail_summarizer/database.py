from datetime import datetime
import os
import json
from google.cloud import secretmanager
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from sentence_transformers import SentenceTransformer

# -- embedding model --
model = SentenceTransformer('all-MiniLM-L6-v2')

#google secret einholen wenn in google ausgeführt
def access_secret(secret_id: str, project_id: str):
    """Fetch secret from Secret Manager."""
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{project_id}/secrets/{secret_id}/versions/latest"
    response = client.access_secret_version(request={"name": name})
    return response.payload.data.decode("UTF-8")

# Service Account Schlüssel laden 
# Unterscheidung für lokale Ausführung und über Cloud Console
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
        #wenn lokale Ausführung
        print(f"Falling back to local serviceAccountKey.json file. Reason: {e}")
        cred = credentials.Certificate("serviceAccountKey.json")

    if not firebase_admin._apps:
        initialize_app(cred)

initialize_firebase()

# Firestore-Client erstellen
db = firestore.client()

#als document ID in der website collection in der Firebase
#wird die url verwendet. Bei dieser müssen jedoch die '/' entfernt/ersetzt werden:
def safe_url(url):
    safe_url = url.replace("/", "-")
    return safe_url


# def add_datarecord(url, category, summary, reading_time, subcategory=None, mail_sent=False,  hn_points=None):
#     timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
#     vector_embedding = model.encode(summary).tolist()
#
#     db.collection("website").document(safe_url(url)).update({
#         "category": category,
#         "summary": summary,
#         "subcategory": subcategory,
#         "mail_sent": mail_sent,
#         "vector_embedding": vector_embedding,
#         "processed": True,
#         "timestamp": timestamp,
#         "reading_time": reading_time,
#         "hn_points": hn_points
#     })
#
#     print(f"Datensatz aktualisiert: {url}")


# neue flexiblere Funktion (muss noch ausgiebig getestet werden
def add_datarecord(url, category=None, summary=None, reading_time=None, subcategory=None, mail_sent=False, hn_points=None):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    update_data = {"processed": True, "timestamp": timestamp, "url": url}  # URL hier hinzufügen

    if category:
        update_data["category"] = category
    if summary is not None:
        update_data["summary"] = summary
    if reading_time is not None:
        update_data["reading_time"] = reading_time
    if subcategory is not None:
        update_data["subcategory"] = subcategory
    if mail_sent is not None:
        update_data["mail_sent"] = mail_sent
    if hn_points is not None:
        update_data["hn_points"] = hn_points

    db.collection("website").document(safe_url(url)).set(update_data, merge=True)
    print(f"Datensatz aktualisiert: {url} | Felder: {list(update_data.keys())}")





def is_duplicate_url(url):
    doc = db.collection("website").document(safe_url(url)).get()
    return doc.exists


from datetime import datetime, timedelta



# database.py
def get_unsent_entries():
    print("[INFO] Lade Einträge aus Firestore mit mail_sent=False ...")
    try:
        query = db.collection('website').where('mail_sent', '==', False).stream()
    except Exception as e:
        print(f"[ERROR] Fehler beim Abrufen der Einträge: {e}")
        return []

    entries = []
    for doc in query:
        data = doc.to_dict() or {}
        url = data.get("url")

        if not url or not isinstance(url, str):
            print(f"[WARN] Überspringe Eintrag ohne gültige URL: {data}")
            continue

        entry = {
            "doc_id": doc.id,                       # nützlich, um später gezielt zu markieren
            "url": url,
            "category": data.get("category"),
            "summary": data.get("summary"),
            "subcategory": data.get("subcategory"),
            "reading_time": data.get("reading_time"),
            "hn_points": data.get("hn_points"),
            "timestamp": data.get("timestamp"),
        }
        entries.append(entry)
        print(f"[DEBUG] Hinzugefügt: {entry['url']} (Kategorie: {entry['category']}, Subkategorie: {entry['subcategory']})")

    print(f"[INFO] Insgesamt {len(entries)} Einträge mit mail_sent=False gefunden.")
    return entries



def mark_as_sent(entries):
    for entry in entries:
        url = entry.get("url")
        if not url:
            print(f"[WARN] Kein URL-Feld für Eintrag: {entry}")
            continue  # Überspringe diesen Eintrag
        db.collection('website').document(safe_url(url)).update({'mail_sent': True})

    print(f"{len(entries)} Einträge wurden als gesendet markiert.")


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


def add_alert_to_website_collection(url, category):
    doc_ref = db.collection("website").document(safe_url(url))
    update_data = {
        "url": url,
        "alert": True,
        "category": category,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
    }
    doc_ref.set(update_data, merge=True)
    print(f"URL gespeichert/aktualisiert: {url} (Kategorie: {category})")



# holt nur unverarbeitete einträge aus der datenbank
# def get_unprocessed_urls():
#     docs = db.collection("website").where("processed", "==", False).stream()
#     return [doc.to_dict()["url"] for doc in docs]

def get_unprocessed_urls():
    """
    Gibt eine Liste von Dictionaries zurück:
    [
        {"url": "https://example.com", "alert": False},
        {"url": "https://alert.com", "alert": True}
    ]
    """
    # Beispiel: Datenbank-Abfrage
    urls = []
    for doc in db.collection("website").where("processed", "==", False).stream():
        data = doc.to_dict()
        urls.append({
            "url": data.get("url"),
            "alert": data.get("alert", False)  # Standard False
        })
    return urls


def mark_unsent_as_sent():
    query = db.collection('website').where('mail_sent', '==', False).stream()

    count = 0
    for doc in query:
        db.collection('website').document(doc.id).update({
            'mail_sent': True
        })
        print("done")
        count += 1

    print(f"[INFO] mail_sent für {count} Einträge (mail_sent=False) auf True gesetzt.")

def is_alert(url):
    doc_ref = db.collection("website").document(safe_url(url)).get()
    if doc_ref.exists:
        data = doc_ref.to_dict()
        return data.get("alert", False)
    return False

# mark_unsent_as_sent()