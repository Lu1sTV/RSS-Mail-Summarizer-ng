import os
import time
from utils.extract_html_content import extract_links_from_rss, download_webpages_concurrently, download_webpages_sequentially, extract_text
from utils.change_trafilatura import change_download_timeout
from llm_calls import summarise_and_categorize_websites
from send_mail import send_mail, create_markdown_report
from dotenv import load_dotenv
from database import add_datarecord, is_duplicate_url, get_summaries_by_category, update_subcategories_in_db, get_unsent_entries


start_time = time.time()
load_dotenv()

rss_url = "https://mstdn.social/@pinboard_pop.rss"

# links = extract_links_from_rss(rss_url)
links = ["https://neal.fun/"]
change_download_timeout(3)
webpages = download_webpages_concurrently(links)
extracted_text, extracted_metadata = extract_text(webpages) # ist noch sequenziell, dauert aber nur ca. 0,5s
# das folgende programm wird nur für die "neuen" urls durchlaufen
cleaned_text = extracted_text.copy()
for url in extracted_text.keys():
        if is_duplicate_url(url):
            del cleaned_text[url]



summaries_and_categories, javascript_required_urls = summarise_and_categorize_websites(cleaned_text)
for url in summaries_and_categories:
    print(f"URL: {url}")
    category = summaries_and_categories[url]["category"]
    print(f"Kategorie: {category}")

    subcategory = summaries_and_categories[url]["subcategory"]
    if subcategory:
        print(f"Subkategorie: {subcategory}")

    summary = summaries_and_categories[url]["summary"]
    print(f"Zusammenfassung: {summary}")

    add_datarecord(url, extracted_text[url], category, summary, subcategory=subcategory)
    print()

# Ausgabe der URLs, die JavaScript benötigen - funktioniert noch nicht zuverlässig
print("Websites, die JavaScript benötigen:")
for url in javascript_required_urls:
    print(url)

# create and send mail
markdown_report_path = "markdown_report.md"

sender_email = "projekt.dhbwrav@gmail.com"
sender_password = os.getenv("SENDER_PASSWORD")
recipient_email = "projekt.dhbwrav@gmail.com"

markdown_report = create_markdown_report(summaries_and_categories, markdown_report_path)

send_mail(sender_email=sender_email, sender_password=sender_password, recipient_email=recipient_email,
          subject="News of the day summarized", mail_body_file=markdown_report_path)

end_time = time.time()
elapsed_time = end_time - start_time  # Berechne die verstrichene Zeit
print(f"Das Programm benötigte {elapsed_time:.2f} Sekunden.")


