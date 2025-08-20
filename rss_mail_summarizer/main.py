## DIe Mail wird nicht gesendet, da nicht jeder der Artikel, der von get_unsent_entries() gefunden wird auch alle nötigen felder hat ??

import os
import time
import traceback

from llm_calls import summarise_and_categorize_websites, summarise_websites
from send_mail import send_mail, create_markdown_report
from dotenv import load_dotenv
from database import add_datarecord, is_duplicate_url
import functions_framework
from database import get_unprocessed_urls
from utils.split_links import split_links_by_github
from mastodon_connector import fetch_and_store_mastodon_links
from hn_popularity import fetch_hn_points

# Es war notwendig diese Funktion auch in Main zu tun für Google Build.
#alternativ wäre ein neuer Unterordner mit einer "main.py" möglich
#dann auch cloudbuild.yaml anpassen
#für lokales laufen diese beiden Zeilen (wenn gewollt) einfach auskommentieren
def mastodon_connector_activate(request):
    fetch_and_store_mastodon_links()
    return "OK", 200


@functions_framework.http
def main(request=None):
    try:
        start_time = time.time()
        load_dotenv()

        all_links = get_unprocessed_urls()

        if not all_links:
            print("Keine neuen Links zum Verarbeiten gefunden.")
        else:
            print(f"{len(all_links)} neue Links in der Datenbank gefunden")

            summaries_and_categories = summarise_and_categorize_websites(all_links)
            
            for url, r in summaries_and_categories.items():
                points = fetch_hn_points(url)
                r["hn_points"] = points


            if not summaries_and_categories:
                print("Es konnten keine Zusammenfassungen erstellt werden.")
            else:
                print("Alle Links erfolgreich verarbeitet und gespeichert.")

                # Ergebnisse in DB schreiben, mail_sent = false
                for url, result in summaries_and_categories.items():
                    add_datarecord(
                        url=url,
                        category=result.get("category"),
                        summary=result.get("summary"),
                        subcategory=result.get("subcategory"),
                        reading_time=result.get("reading_time"),
                        hn_points=result.get("hn_points"),
                        mail_sent=False  # Wichtig: explizit False setzen
                    )

        # 2️⃣ Schritt: Mailversand für alle ungesendeten Artikel
        from database import get_unsent_entries, mark_as_sent
        unsent_entries = get_unsent_entries()

        if not unsent_entries:
            print("Keine ungesendeten Artikel gefunden. Mailversand übersprungen.")
        else:
            print(f"{len(unsent_entries)} ungesendete Artikel gefunden – Report wird erstellt.")

            markdown_report_path = "markdown_report.md"
            sender_email = "projekt.dhbwrav@gmail.com"
            sender_password = os.getenv("SENDER_PASSWORD")
            recipient_email = "projekt.dhbwrav@gmail.com"

            # Report aus DB-Daten erstellen
            summaries_from_db = {
                entry["url"]: {
                    "category": entry.get("category"),
                    "subcategory": entry.get("subcategory"),
                    "summary": entry.get("summary"),
                    "reading_time": entry.get("reading_time")
                }
                for entry in unsent_entries
            }


            create_markdown_report(summaries_from_db, markdown_report_path)
            print("Markdown Report erstellt.")

            # Mail senden
            send_mail(
                sender_email=sender_email,
                sender_password=sender_password,
                recipient_email=recipient_email,
                subject="News of the day summarized",
                mail_body_file=markdown_report_path
            )

            # Artikel in DB als gesendet markieren
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



