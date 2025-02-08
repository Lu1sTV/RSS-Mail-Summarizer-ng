import os
from utils.extract_html_content import extract_links_from_rss, download_webpages, extract_text
from utils.change_trafilatura import change_download_timeout
from llm_calls import summarise_website, categorize_website
from send_mail import send_mail, create_mail_body
from dotenv import load_dotenv
from database import add_datarecord


load_dotenv()

rss_url = "https://mstdn.social/@pinboard_pop.rss"

links = extract_links_from_rss(rss_url)
change_download_timeout(10)
webpages = download_webpages(links)
extracted_text, extracted_metadata = extract_text(webpages)

for link, text in extracted_text.items():
    print(link)

    category, subcategory = categorize_website(text)
    print("Category: " + category)
    if category != "Uncategorized":
        print("Subcategory: " + subcategory)

    summary = summarise_website(text)
    print("Summary: " + summary)

    add_datarecord(url=link, html_text=text, category=category, subcategory=subcategory, summary=summary)
    print("--------------------------")


# send email
sender_email = "projekt.dhbwrav@gmail.com"
sender_password = os.getenv("SENDER_PASSWORD")
recipient_email = "projekt.dhbwrav@gmail.com"

mail_body_file = "mail_body.md"
mail_body = create_mail_body(mail_body_file)
send_mail(sender_email=sender_email, sender_password=sender_password, recipient_email=recipient_email,
          subject="News of the day summarized", mail_body_file=mail_body_file)