import os
import time
from utils.extract_html_content import extract_links_from_rss, download_webpages_concurrently, download_webpages_sequentially, extract_text
from utils.change_trafilatura import change_download_timeout
from llm_calls import summarise_website, categorize_website, get_subcategories
from send_mail import send_mail, create_markdown_report
from dotenv import load_dotenv
from database import add_datarecord, is_duplicate_url, get_summaries_by_category, update_subcategories_in_db, get_unsent_entries

start_time = time.perf_counter()

load_dotenv()

rss_url = "https://mstdn.social/@pinboard_pop.rss"

links = extract_links_from_rss(rss_url)
#links = ['https://www.washingtonpost.com/politics/2025/02/02/usaid-trump-musk/', 'https://www.cbc.ca/news/canada/toronto/ford-ripping-up-province-contract-with-starlink-1.7448763']
change_download_timeout(3)
webpages = download_webpages_concurrently(links)
extracted_text, extracted_metadata = extract_text(webpages)

extract_time = time.perf_counter()

for link, text in extracted_text.items():

    if is_duplicate_url(link):
            print(f"URL has already been summarized: {link}")
            continue

    print(link)

    category = categorize_website(text)
    print("Category: " + category)

    summary = summarise_website(text)
    print("Summary: " + summary)

    add_datarecord(url=link, html_text=text, category=category, summary=summary)
    print("--------------------------")

llm_before_subkategories = time.perf_counter()

# dictionary with category as key and list of dictionaries as values
# list of dictionaries has subcategories as keys and urls as values
subcategories_for_each_category = {}

summaries_by_category = get_summaries_by_category()
if summaries_by_category:
    for category, list_of_summaries in summaries_by_category.items():
        subcategories = get_subcategories(list_of_summaries)
        if subcategories is not None:
            subcategories_for_each_category[category] = subcategories


# Update the database with the assigned subcategories
update_subcategories_in_db(subcategories_for_each_category)

llm_time = time.perf_counter()

# create and send mail
markdown_report_path = "markdown_report.md"

sender_email = "projekt.dhbwrav@gmail.com"
sender_password = os.getenv("SENDER_PASSWORD")
recipient_email = "projekt.dhbwrav@gmail.com"

unsent_entries = get_unsent_entries()
markdown_report = create_markdown_report(unsent_entries, markdown_report_path)

send_mail(sender_email=sender_email, sender_password=sender_password, recipient_email=recipient_email,
          subject="News of the day summarized", mail_body_file=markdown_report_path)

completion_time = time.perf_counter()

print(f"Time to extract: {extract_time - start_time:.2f} seconds \n")
print(f"Time to summarize and add to Firebase: {llm_before_subkategories - start_time:.2f} seconds \n")
print(f"Time to llm + subkategories: {llm_time - start_time:.2f} seconds \n")
print(f"Time to complete: {completion_time - start_time:.2f} seconds \n")