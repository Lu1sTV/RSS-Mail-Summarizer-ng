import re
import sqlite3
from datetime import datetime

conn = sqlite3.connect('RSS_feed.db')
c = conn.cursor()

#create table
c.execute("""CREATE TABLE IF NOT EXISTS website (
    url TEXT, 
    html TEXT, 
    was_summarized INTEGER, 
    summary TEXT, 
    category TEXT, 
    subcategory TEXT, 
    mail_sent INTEGER DEFAULT 0, 
    timestamp TEXT
)""")

conn.commit()


def add_datarecord(url, html_text, category, summary,subcategory=None, mail_sent=False):
    conn = sqlite3.connect('RSS_feed.db')
    c = conn.cursor()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")

    c.execute("""
        INSERT INTO website (url, html, category, subcategory, was_summarized, summary, mail_sent, timestamp)
        VALUES (?, ?, ?, ?, 0, ?, ?, ?)
    """, (url, html_text, category, subcategory, summary, int(mail_sent), timestamp))

    conn.commit()
    conn.close()

    print(f"Datarecord {url} added to database")
    
def is_duplicate_url(url):
    conn = sqlite3.connect('RSS_feed.db')
    c = conn.cursor()
    c.execute("SELECT url FROM website WHERE url = ?", (url,))
    result = c.fetchone()
    conn.close()
    return result is not None


def get_unsent_entries():
    conn = sqlite3.connect('RSS_feed.db')
    c = conn.cursor()

    # Alle Einträge mit mail_sent == 0 abfragen
    c.execute("SELECT url, category, summary, subcategory FROM website WHERE mail_sent = 0")
    entries = c.fetchall()

    conn.close()

    return entries


def mark_as_sent(entries):
    conn = sqlite3.connect('RSS_feed.db')
    c = conn.cursor()

    for entry in entries:
        url = entry[0]
        c.execute("UPDATE website SET mail_sent = 1 WHERE url = ?", (url,))

    conn.commit()
    conn.close()
    print("Entries marked as sent.")


# Nur für Testzwecke nutzen
def reset_last_20_entries():
    # Verbindung zur Datenbank herstellen
    conn = sqlite3.connect('RSS_feed.db')
    c = conn.cursor()

    # Die letzten 20 Einträge mit mail_sent = 0 auswählen (nach timestamp sortiert)
    c.execute("""
        SELECT url FROM website WHERE mail_sent = 1 ORDER BY timestamp DESC LIMIT 20
    """)
    entries = c.fetchall()

    if entries:
        # Für jedes Entry den mail_sent Wert auf 0 setzen
        for entry in entries:
            url = entry[0]
            c.execute("UPDATE website SET mail_sent = 0 WHERE url = ?", (url,))

        conn.commit()
        print(f"Successfully reset 'mail_sent' to 0 for {len(entries)} entries.")
    else:
        print("No entries found to reset.")

    conn.close()


def get_summaries_by_category():
    conn = sqlite3.connect("RSS_feed.db")
    cursor = conn.cursor()

    # Select categories with at least 4 unsent emails
    cursor.execute("""
        SELECT category
        FROM website
        WHERE mail_sent = 0
        GROUP BY category
        HAVING COUNT(*) >= 4
    """)

    categories = cursor.fetchall()

    summaries_by_category = {}

    # For each category, retrieve summaries and URLs
    for (category,) in categories:
        cursor.execute("""
            SELECT summary, url
            FROM website
            WHERE category = ? AND mail_sent = 0
        """, (category,))

        # Retrieve summaries and URLs for the current category
        summaries = cursor.fetchall()
        summaries_by_category[category] = [{"summary": summary, "url": url} for summary, url in summaries]

    conn.close()

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
    conn = sqlite3.connect("RSS_feed.db")
    cursor = conn.cursor()

    for category, subcategories in subcategories_for_each_category.items():
        for subcategory, urls in subcategories.items():
            for url in urls:
                # Update the subcategory for each URL in the database
                cursor.execute("""
                    UPDATE website
                    SET subcategory = ?
                    WHERE url = ?
                """, (subcategory, url))

    conn.commit()
    conn.close()

