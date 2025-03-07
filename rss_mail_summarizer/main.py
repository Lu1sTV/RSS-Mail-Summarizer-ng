import os
import time
from utils.extract_html_content import extract_links_from_rss
from llm_calls import summarise_and_categorize_websites
from send_mail import send_mail, create_markdown_report
from dotenv import load_dotenv
from database import add_datarecord, is_duplicate_url
import functions_framework

@functions_framework.http
def main(request):
    try:
        start_time = time.time()
        load_dotenv()

        rss_url = "https://mstdn.social/@pinboard_pop.rss"
        links = extract_links_from_rss(rss_url)

        # Entferne Duplikate
        for link in links[:]:
            if is_duplicate_url(link):
                print(f"URL has already been summarized: {link}")
                links.remove(link)

        summaries_and_categories = summarise_and_categorize_websites(links)

        for url in summaries_and_categories:
            print(f"URL: {url}")
            category = summaries_and_categories[url]["category"]
            print(f"Kategorie: {category}")
            subcategory = summaries_and_categories[url]["subcategory"]
            if subcategory:
                print(f"Subkategorie: {subcategory}")
            summary = summaries_and_categories[url]["summary"]
            print(f"Zusammenfassung: {summary}")
            add_datarecord(url, category, summary, subcategory=subcategory)
            print()

        # Erstelle und versende den Report
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

        end_time = time.time()
        elapsed_time = end_time - start_time
        print(f"Das Programm benötigte {elapsed_time:.2f} Sekunden.")

        return "Funktion erfolgreich ausgeführt", 200
    except Exception as e:
        return f"Fehler: {e}", 500

