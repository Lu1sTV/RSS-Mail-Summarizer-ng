## DIe Mail wird nicht gesendet, da nicht jeder der Artikel, der von get_unsent_entries() gefunden wird auch alle nötigen felder hat ??

import os
import time
import traceback

from llm_calls import summarise_and_categorize_websites, summarise_alerts
from send_mail import send_mail, create_markdown_report
from dotenv import load_dotenv
from database import add_datarecord, is_duplicate_url, is_alert
import functions_framework
from database import get_unprocessed_urls
from utils.split_links import split_links_by_github
from mastodon_connector import fetch_and_store_mastodon_links
from utils.hn_popularity import fetch_hn_points
from alerts_connector import list_google_alerts

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

        list_google_alerts()

        all_links = get_unprocessed_urls()

        if not all_links:
            print("Keine neuen Links zum Verarbeiten gefunden.")
        else:
            print(f"{len(all_links)} neue Links in der Datenbank gefunden")

            # 🔹 Normale Links (ohne alert)
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

            # 🔹 Alert-Links separat verarbeiten
            alert_links_dict = {}  # Dictionary {label: [urls]}
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
                        mail_sent=False
                    )
                print(f"{len(alert_summaries)} Alerts erfolgreich verarbeitet.")

        # 2️⃣ Mailversand für normale ungesendete Artikel
        from database import get_unsent_entries, mark_as_sent
        unsent_entries = get_unsent_entries()  # Alerts vom Report ausschließen

        if not unsent_entries:
            print("Keine ungesendeten Artikel gefunden. Mailversand übersprungen.")
        else:
            print(f"{len(unsent_entries)} ungesendete Artikel gefunden – Report wird erstellt.")

            markdown_report_path = "markdown_report.md"
            sender_email = "projekt.dhbwrav@gmail.com"
            sender_password = os.getenv("SENDER_PASSWORD")
            recipient_email = "projekt.dhbwrav@gmail.com"

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

            create_markdown_report(summaries_from_db, markdown_report_path)
            print("Markdown Report erstellt.")

            send_mail(
                sender_email=sender_email,
                sender_password=sender_password,
                recipient_email=recipient_email,
                subject="News of the day summarized",
                mail_body_file=markdown_report_path
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


# ToDo für alerts
# summarise_alerts funktion schreiben                               -> done but not testet
# filter funktion so ändern, dass sie in list_google_alerts ist     -> done
# links mit alert=true in die datenbank schreiben                   -> done
# zweite database funktion, die summary und mail_sent hinzufügt     -> done but not testet
# alerts_connector in die main und per scheduler ausführen

# alle datenbank einträge über eine zentrale funktion (add_datarecord)
