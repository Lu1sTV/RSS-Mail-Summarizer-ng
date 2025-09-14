"""
Diese Datei ist die Hauptdatei des Projekts.
Sie definiert drei Entry-Points für Google Cloud Functions:

1. mastodon_connector_activate(request)
   - Ruft über den Mastodon-Connector Links ab und speichert diese.

2. call_alerts(request)
   - Ruft Google Alerts ab, extrahiert die URLs und speichert sie in der Datenbank.

3. main(request)
   - Hauptfunktion zum Verarbeiten aller Links aus der Datenbank.
   - Extrahiert und kategorisiert Inhalte, berechnet HN-Punkte, speichert die Ergebnisse in der Datenbank
     und versendet den E-Mail-Report.

Lokales Testen:
- Die Funktion `main()` kann lokal getestet werden, ohne Cloud Functions zu deployen.
  Dazu einfach das Skript direkt ausführen (`python main.py`)
- Alerts und Mastodon-Integration sollten separat über die Dateien `alerts_connector`
  bzw. `mastodon_connector` getestet werden, um die jeweiligen
  Funktionen isoliert zu prüfen.
"""

#package imports
import os
import time
import traceback
from dotenv import load_dotenv
import functions_framework

#Imports eigener Funktionen
from alerts_connector import list_google_alerts
from database import add_datarecord, get_unprocessed_urls, get_unsent_entries, mark_as_sent
from llm_calls import summarise_and_categorize_websites, summarise_alerts
from mastodon_connector import fetch_and_store_mastodon_links
from send_mail import send_mail, create_markdown_report
from utils.hn_popularity import fetch_hn_points

load_dotenv()

MARKDOWN_REPORT_PATH = "markdown_report.md"
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")

print("test")

def mastodon_connector_activate(request):
    fetch_and_store_mastodon_links()
    return "OK", 200

@functions_framework.http
def call_alerts(request=None):
    try:
        urls = list_google_alerts()
        print("Alerts erfolgreich verarbeitet:", urls)
        return {"status": "ok", "urls": urls}, 200
    except Exception as e:
        print("[ERROR] Unhandled exception in call_alerts():", e)
        return f"Fehler: {e}", 500


"""
Hauptfunktion zur Verarbeitung der gespeicherten Links:

1. Abruf aller unprocessed URLs aus der Datenbank.
2. Verarbeitung normaler Links (ohne Alerts):
   - Inhalte zusammenfassen
   - Hacker News Punkte berechnen
   - Ergebnisse in der Datenbank speichern
3. Verarbeitung von Alert-Links:
   - Gruppierung nach Alert-Label
   - Inhalte zusammenfassen
   - Ergebnisse speichern, Feld 'processed' auf True setzen
4. Erstellung und Versand des täglichen Markdown-E-Mail-Reports für normale Artikel
   - Unsent Entries abrufen
   - Report erstellen
   - E-Mail versenden
   - Artikel als gesendet markieren
"""
@functions_framework.http
def main(request=None):
    try:
        start_time = time.time()

        all_links = get_unprocessed_urls()

        if not all_links:
            print("Keine neuen Links zum Verarbeiten gefunden.")
        else:
            print(f"{len(all_links)} neue Links in der Datenbank gefunden")

            # Normale Links (ohne alerts)
            normal_links = [link["url"] for link in all_links if not link.get("alert")]
            if normal_links:
                summaries_and_categories = summarise_and_categorize_websites(normal_links)
                for url, result in summaries_and_categories.items():
                    points = fetch_hn_points(url)
                    result["hn_points"] = points
                    add_datarecord(
                        url=url,
                        category=result.get("category"),
                        summary=result.get("summary"),
                        subcategory=result.get("subcategory"),
                        reading_time=result.get("reading_time"),
                        hn_points=result.get("hn_points"),
                        mail_sent=False
                    )
                print(f"{len(summaries_and_categories)} normale Links erfolgreich verarbeitet.")

            # Alert-Links separat verarbeiten
            alert_links_dict = {}
            for link in all_links:
                if link.get("alert"):
                    label = link.get("alert_label", "Unbekannt")
                    alert_links_dict.setdefault(label, []).append(link["url"])

            if alert_links_dict:
                alert_summaries = summarise_alerts(alert_links_dict)
                for url, result in alert_summaries.items():

                    add_datarecord(
                        url=url,
                        summary=result.get("summary"),
                        reading_time=result.get("reading_time"),
                        mail_sent=False,
                        processed=True
                    )
                print(f"{len(alert_summaries)} Alerts erfolgreich verarbeitet.")

        # Mailversand für normale ungesendete Artikel
        unsent_entries = get_unsent_entries()

        if not unsent_entries:
            print("Keine ungesendeten Artikel gefunden. Mailversand übersprungen.")
        else:
            print(f"{len(unsent_entries)} ungesendete Artikel gefunden – Report wird erstellt.")


            summaries_from_db = {
                entry["url"]: {
                    "category": entry.get("category"),
                    "subcategory": entry.get("subcategory"),
                    "summary": entry.get("summary"),
                    "reading_time": entry.get("reading_time"),
                    "hn_points": entry.get("hn_points"),
                    "alert": entry.get("alert", False)
                }
                for entry in unsent_entries
            }

            create_markdown_report(summaries_from_db, MARKDOWN_REPORT_PATH)
            print("Markdown Report erstellt.")

            send_mail(
                sender_email=SENDER_EMAIL,
                recipient_email=RECIPIENT_EMAIL,
                subject="News of the day summarized",
                mail_body_file=MARKDOWN_REPORT_PATH
            )

            mark_as_sent(unsent_entries)
            print("Artikel in der DB als gesendet markiert.")

        elapsed_time = time.time() - start_time
        print(f"Funktion abgeschlossen in {elapsed_time:.2f} Sekunden.")
        return "Funktion erfolgreich ausgeführt", 200

    except Exception as e:
        print("[ERROR] Unhandled exception in main():", e)
        traceback.print_exc()
        return f"Fehler: {e}", 500



if __name__ == '__main__':
    main()



