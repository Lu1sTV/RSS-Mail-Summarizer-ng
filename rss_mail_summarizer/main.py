import os
import time
from llm_calls import summarise_and_categorize_websites
from send_mail import send_mail, create_markdown_report
from dotenv import load_dotenv
from database import add_datarecord, is_duplicate_url
import functions_framework
from database import get_unprocessed_urls

@functions_framework.http
def main(request=None):
    try:
        start_time = time.time()
        load_dotenv()


        links = get_unprocessed_urls()

        if not links:
            print("Keine neuen Links zum Verarbeiten gefunden.")
            return "Keine neuen Links gefunden.", 200

        summaries_and_categories = summarise_and_categorize_websites(links)

        for url in summaries_and_categories:
            result = summaries_and_categories[url]
            add_datarecord(
                url=url,
                category=result["category"],
                summary=result["summary"],
                subcategory=result.get("subcategory")
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

