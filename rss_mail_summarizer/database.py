from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

# Service Account Schlüssel laden
cred = credentials.Certificate("serviceAccountKey.json")
firebase_admin.initialize_app(cred)

# Firestore-Client erstellen
db = firestore.client()

#als document ID in der website collection in der Firebase
#wird die url verwendet. Bei dieser müssen jedoch die '/' entfernt/ersetzt werden:
def safe_url(url):
    safe_url = url.replace("/", "-")
    return safe_url


def add_datarecord(url, category, summary,subcategory=None, mail_sent=False):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    db.collection("website").document(safe_url(url)).set({
        "url": url,
        "category": category,
        "summary": summary,
        "subcategory": subcategory,
        "mail_sent": mail_sent,
        "timestamp": timestamp   
    }, merge=True)


    print(f"a datarecord for {url} was added")

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

            entries.append((url, category, summary, subcategory))
    
    # entries is a list of tuples with the following information: (url, category, summary, subcategory)
    return entries



def mark_as_sent(entries):
    # entries = [] 

    for entry in entries:
        url = entry[0]
        db.collection('website').document(safe_url(url)).update({'mail_sent': True})

    print("Entries marked as sent.")

