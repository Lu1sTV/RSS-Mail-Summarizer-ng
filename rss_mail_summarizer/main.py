import os
from utils.extract_html_content import extract_links_from_rss, download_webpages, extract_text
from utils.change_trafilatura import change_download_timeout
from llm_calls import summarise_website, categorize_website
from send_mail import send_mail
from dotenv import load_dotenv
from database import add_datarecord


load_dotenv()

rss_url = "https://mstdn.social/@pinboard_pop.rss"
long_term_cache = "cache_files/long_term_cache.txt"
short_term_cache = "cache_files/short_term_cache.txt"

links = extract_links_from_rss(rss_url)
change_download_timeout(10)
webpages = download_webpages(links)
extracted_text, extracted_metadata = extract_text(webpages)

# delete short term cache before every run to make sure an empty file is created
if os.path.exists(short_term_cache):
    os.remove(short_term_cache)

with open(short_term_cache, "a") as file:

    for link, text in extracted_text.items():
        print(link)
        file.write("URL: " + link + "\n")

        category = categorize_website(text)
        print("Category: " + category)
        file.write("Category: " + category + ":\n")

        summary = summarise_website(text)
        print("Summary: " + summary)
        file.write("Summary: " + summary + "\n\n")

        add_datarecord(link, text, category, summary)
        print("--------------------------")

# append short term cache to long term cache
# Duplikatserkennung muss noch ergänzt werden
with open(short_term_cache, "r") as src, open(long_term_cache, "a") as dest:
    dest.write(src.read())

# send email
with open("cache_files/short_term_cache.txt", "r", encoding="utf-8") as file:
    email_body = file.read()
sender_email = "projekt.dhbwrav@gmail.com"
sender_password = os.getenv("SENDER_PASSWORD")
recipient_email = "projekt.dhbwrav@gmail.com"
send_mail(sender_email, sender_password, recipient_email, "News of the day summarized", email_body)