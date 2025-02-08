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


def add_datarecord(url, html_text, category, subcategory, summary, mail_sent=False):
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


def get_unsent_entries():
    conn = sqlite3.connect('RSS_feed.db')
    c = conn.cursor()

    # Alle Einträge mit mail_sent == 0 abfragen
    c.execute("SELECT url, category, subcategory, summary FROM website WHERE mail_sent = 0")
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




#SO GEHT EIN SELECT, FALLS DAS BENÖTIGT WIRD:
#c.execute("SELECT * FROM website WHERE was_summarized = 0")
#c.fetchone()
#c.fetchmany(2)
#print(c.fetchall())


#conn.commit()