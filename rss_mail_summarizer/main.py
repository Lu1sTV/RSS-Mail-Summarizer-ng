import os
import time
from llm_calls import summarise_and_categorize_websites, summarise_websites
from send_mail import send_mail, create_markdown_report
from dotenv import load_dotenv
from database import add_datarecord, is_duplicate_url
import functions_framework
from database import get_unprocessed_urls
from utils.split_links import split_links_by_github
from mastodon_connector import fetch_and_store_mastodon_links as target

#another test again

# Es war notwendig diese Funktion auch in Main zu tun für Google Build.
#alternativ wäre ein neuer Unterordner mit einer "main.py" möglich 
#dann auch cloudbuild.yaml anpassen
#für lokales laufen diese beiden Zeilen (wenn gewollt) einfach auskommentieren
def fetch_and_store_mastodon_links(request):
    return target(request)


@functions_framework.http
def main(request=None):
    try:
        start_time = time.time()
        load_dotenv()


        all_links = get_unprocessed_urls()

        if not all_links:
            print("Keine neuen Links zum Verarbeiten gefunden.")
            return "Keine neuen Links gefunden.", 200
        
        github_links, links = split_links_by_github(all_links)

        results_default = summarise_and_categorize_websites(links)
        results_github = summarise_websites(github_links)
        summaries_and_categories = {**results_default, **results_github}

        for url in summaries_and_categories:
            result = summaries_and_categories[url]
            add_datarecord(
                url=url,
                category=result["category"],
                summary=result["summary"],
                subcategory=result.get("subcategory"),
                reading_time=result.get("reading_time")
            )

        # Markdown Report und Mail
        markdown_report_path = "markdown_report.md"
        sender_email = "projekt.dhbwrav@gmail.com"
        sender_password = os.getenv("SENDER_PASSWORD")
        recipient_email = "projekt.dhbwrav@gmail.com"

        markdown_report = create_markdown_report(summaries_and_categories, markdown_report_path)

        send_mail(
            sender_email=sender_email,
            sender_password=sender_password,
            recipient_email=recipient_email,
            subject="News of the day summarized",
            mail_body_file=markdown_report_path
        )

        elapsed_time = time.time() - start_time
        print(f"Funktion abgeschlossen in {elapsed_time:.2f} Sekunden.")
        return "Funktion erfolgreich ausgeführt", 200

    except Exception as e:
        return f"Fehler: {e}", 500


if __name__ == '__main__':
    main()



