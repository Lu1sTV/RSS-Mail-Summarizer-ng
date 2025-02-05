import sqlite3
from datetime import datetime

conn = sqlite3.connect('RSS_feed.db')

c = conn.cursor()

#create table
c.execute("""CREATE TABLE IF NOT EXISTS website (url TEXT, html TEXT, was_summarized INTEGER, summary TEXT, category TEXT, timestamp TEXT)""")
conn.commit()

def add_datarecord(url, html_text, category, summary):
    timestamp = datetime.now()
    c.execute(f"INSERT INTO website (url, html, category, was_summarized, summary, timestamp) VALUES (?, ?, ?, 0, ?, ?)", (url, html_text, category, summary, timestamp))
    conn.commit()
    #print(f"Datarecord:  {url},   {category}")


#SO GEHT EIN SELECT, FALLS DAS BENÖTIGT WIRD:
#c.execute("SELECT * FROM website WHERE was_summarized = 0")
#c.fetchone()
#c.fetchmany(2)
#print(c.fetchall())



#conn.commit()