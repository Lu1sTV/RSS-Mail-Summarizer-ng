import os
from utils.extract_html_content import extract_links_from_rss, download_webpages, extract_text
from utils.change_trafilatura import change_download_timeout
from llm_calls import summarise_website, categorize_website, get_subcategories
from send_mail import send_mail, create_mail_body
from dotenv import load_dotenv
from database import add_datarecord, is_duplicate_url, get_summaries_by_category, update_subcategories_in_db



load_dotenv()

rss_url = "https://mstdn.social/@pinboard_pop.rss"

links = extract_links_from_rss(rss_url)
change_download_timeout(10)
webpages = download_webpages(links)
extracted_text, extracted_metadata = extract_text(webpages)

for link, text in extracted_text.items():
    
    if is_duplicate_url(link):
            print(f"URL bereits verarbeitet: {link} -> Überspringe Verarbeitung.")
            continue

    print(link)

    category = categorize_website(text)
    print("Category: " + category)

    summary = summarise_website(text)
    print("Summary: " + summary)

    add_datarecord(url=link, html_text=text, category=category, summary=summary)
    print("--------------------------")


# dictionary with category as key and list of dictionaries as values
# list of dictionaries has subcategories as keys and urls as values
subcategories_for_each_category = {}

summaries_by_category = get_summaries_by_category()
if summaries_by_category is not {}:
    for category, list_of_summaries in summaries_by_category.values():
        subcategories = get_subcategories(list_of_summaries)
        if subcategories is not None:
            subcategories_for_each_category[category] = subcategories

# Update the database with the assigned subcategories
update_subcategories_in_db(subcategories_for_each_category)


# send email
sender_email = "projekt.dhbwrav@gmail.com"
sender_password = os.getenv("SENDER_PASSWORD")
recipient_email = "projekt.dhbwrav@gmail.com"

mail_body_file = "mail_body.md"
mail_body = create_mail_body(mail_body_file)
send_mail(sender_email=sender_email, sender_password=sender_password, recipient_email=recipient_email,
          subject="News of the day summarized", mail_body_file=mail_body_file)