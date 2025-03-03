import json
import os
from datetime import datetime
import firebase_admin
from firebase_admin import credentials, firestore

import urllib.parse


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


def add_datarecord(url, html_text, category, summary,subcategory=None, mail_sent=False):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    db.collection("website").document(safe_url(url)).set({
        "url": url,
        "html": html_text,
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


def mark_all_as_sent():
    websites = db.collection('website').where(field_path="mail_sent", op_string="==", value=False).stream()    
    
    for w in websites:
        db.collection('website').document(w.id).update({'mail_sent': True})

    print("All entries marked as sent")



def mark_as_sent(entries):
    # entries = [] 

    for entry in entries:
        url = entry[0]
        db.collection('website').document(safe_url(url)).update({'mail_sent': True})

    print("Entries marked as sent.")


def get_summaries_by_category():
    websites = db.collection('website').where(field_path="mail_sent", op_string="==", value=False).stream()

    category_counts = {}

    # counts how many articles there are per category (only checks the ones not yet sent in an email)
    for w in websites:
        category = w.get('category')

        if category in category_counts:
            category_counts[category] += 1
        else:
            category_counts[category] = 1
    
    summaries_by_category = {}

    #saves the url and summary of all websites belonging to a category with count >=4
    for category, counts in category_counts.items():
        if counts >=4:
            subcategorise = db.collection('website').where(field_path="mail_sent", op_string="==", value=False).where(field_path="category", op_string="==", value=category).stream()

            for s in subcategorise:
                summaries_by_category[category] = [{"summary": s.get('summary'), "url": s.get('url')}]

    # returns a dictionary with summary, url for the process of subcategorizing relevant articles
    return summaries_by_category



def update_subcategories_in_db(subcategories_for_each_category):
    """
    Update the SQLite database with the assigned subcategories for each URL.

    Input:
    - subcategories_for_each_category (dict): A dictionary where each key is a category,
      and each value is a dictionary with subcategories as keys and lists of URLs as values.

    Example Input:
    {
        "Technology": {
            "AI Applications": [
                "http://example.com/tech1",
                "http://example.com/tech2",
                "http://example.com/tech3",
                "http://example.com/tech4"
            ]
        },
        "Science": {
            "Climate Change": [
                "http://example.com/science1",
                "http://example.com/science2"
            ]
        }
    }
    """


    for category, subcategories in subcategories_for_each_category.items():
        for subcategory, urls in subcategories.items():
            for url in urls:
                # Update the subcategory for each URL in the database
                db.collection("website").document(safe_url(url)).set({"subcategory": subcategory}, merge=True)
