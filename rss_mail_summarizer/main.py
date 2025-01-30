import time
from utils.extract_html_content import extract_links_from_rss, download_webpages, extract_text
from utils.change_trafilatura import change_download_timeout
from llm_calls import summarise_website, categorize_website


rss_url = "https://mstdn.social/@pinboard_pop.rss"


links = extract_links_from_rss(rss_url)
change_download_timeout(10)
webpages = download_webpages(links)

extracted_text, extracted_metadata = extract_text(webpages)

for link, text in extracted_text.items():
    print(link)
    # print(text)
    categorize_website(text)
    summarise_website(text)