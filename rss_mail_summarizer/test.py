import os
from utils.extract_html_content import extract_links_from_rss#, download_webpages, extract_text


#load_dotenv()

rss_url = "https://mstdn.social/@pinboard_pop.rss"

links = extract_links_from_rss(rss_url)

print(type(links))