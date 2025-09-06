"""Dieses Modul enthält die Datenbank-Logik . Hier wird die Verbindung zu Firestore hergestellt und die Speicherung,
Verarbeitung und der Abruf von Website- und Alert-Daten verwaltet.
Es enthält Funktionen zum Hinzufügen neuer Links, Speichern von Zusammenfassungen,
Abrufen ungesendeter Artikel, Markieren als gesendet sowie Hilfsfunktionen wie
das Erkennen von Duplikaten und Unterscheidung zwischen normalen und Alert-Links."""

from datetime import datetime
import os
import json
from dotenv import load_dotenv
from google.cloud import secretmanager
from firebase_admin import credentials, firestore, initialize_app
import firebase_admin
from sentence_transformers import SentenceTransformer

load_dotenv()
SERVICE_ACCOUNT_KEY_PATH = "rss_mail_summarizer/serviceAccountKey.json"
model = SentenceTransformer("all-MiniLM-L6-v2")


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


# Wandelt eine URL in einen Firestore-sicheren String (für Dokument-IDs) um
def safe_url(url):
    safe_url = url.replace("/", "-")
    return safe_url


# Fügt oder aktualisiert einen Datensatz in der Datenbank für eine verarbeitete URL
def add_datarecord(
    url,
    category=None,
    summary=None,
    reading_time=None,
    subcategory=None,
    mail_sent=False,
    hn_points=None,
):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
    update_data = {
        "processed": True,
        "timestamp": timestamp,
        "url": url,
    }
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

    # Aktualisiert oder fügt einen Datensatz in der DB hinzu
    db.collection("website").document(safe_url(url)).set(update_data, merge=True)
    print(f"Datensatz aktualisiert: {url} | Felder: {list(update_data.keys())}")


# Prüft, ob eine URL bereits in der Datenbank existiert
def is_duplicate_url(url):
    doc = db.collection("website").document(safe_url(url)).get()
    return doc.exists


from datetime import datetime, timedelta


# Holt alle Artikel, die noch nicht per Mail gesendet wurden
def get_unsent_entries():
    print("[INFO] Lade Einträge aus Firestore mit mail_sent=False ...")
    try:
        query = db.collection("website").where("mail_sent", "==", False).stream()
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
            "doc_id": doc.id,
            "url": url,
            "category": data.get("category"),
            "summary": data.get("summary"),
            "subcategory": data.get("subcategory"),
            "reading_time": data.get("reading_time"),
            "hn_points": data.get("hn_points"),
            "timestamp": data.get("timestamp"),
        }
        entries.append(entry)
        print(
            f"[DEBUG] Hinzugefügt: {entry['url']} (Kategorie: {entry['category']}, Subkategorie: {entry['subcategory']})"
        )

    print(f"[INFO] Insgesamt {len(entries)} Einträge mit mail_sent=False gefunden.")
    return entries


# Markiert eine übergebene Liste von Artikeln in der Datenbank als gesendet
def mark_as_sent(entries):
    for entry in entries:
        url = entry.get("url")
        if not url:
            print(f"[WARN] Kein URL-Feld für Eintrag: {entry}")
            continue
        db.collection("website").document(safe_url(url)).update({"mail_sent": True})

    print(f"{len(entries)} Einträge wurden als gesendet markiert.")


################################################################


# Fügt eine neue unverarbeitete URL in die Datenbank ein
def add_url_to_website_collection(url):
    doc_ref = db.collection("website").document(safe_url(url))
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.set(
            {
                "url": url,
                "processed": False,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f"),
            }
        )
        print(f"Neue URL gespeichert: {url}")
    else:
        print(f"URL bereits vorhanden (wird ignoriert): {url}")


# Fügt oder aktualisiert eine Alert-URL mit Kategorie in der Datenbank
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


# Holt alle unverarbeiteten URLs (inkl. Info ob es sich um Alerts handelt)
def get_unprocessed_urls():
    """
    Gibt eine Liste von Dictionaries zurück:
    [
        {"url": "https://example.com", "alert": False},
        {"url": "https://alert.com", "alert": True}
    ]
    """
    urls = []
    for doc in db.collection("website").where("processed", "==", False).stream():
        data = doc.to_dict()
        urls.append(
            {
                "url": data.get("url"),
                "alert": data.get("alert", False),
            }
        )
    return urls


# Markiert alle ungesendeten Einträge in der Datenbank als gesendet
def mark_unsent_as_sent():
    query = db.collection("website").where("mail_sent", "==", False).stream()

    count = 0
    for doc in query:
        db.collection("website").document(doc.id).update({"mail_sent": True})
        print("done")
        count += 1

    print(f"[INFO] mail_sent für {count} Einträge (mail_sent=False) auf True gesetzt.")


# Prüft, ob eine bestimmte URL als Alert markiert ist
def is_alert(url):
    doc_ref = db.collection("website").document(safe_url(url)).get()
    if doc_ref.exists:
        data = doc_ref.to_dict()
        return data.get("alert", False)
    return False
