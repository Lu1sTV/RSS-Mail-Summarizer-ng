import concurrent.futures

import requests
from bs4 import BeautifulSoup
from trafilatura import fetch_url, extract, fetch_response


def extract_links_from_rss(rss_url):
    try:
        response = requests.get(rss_url)
        response.raise_for_status()

        soup = BeautifulSoup(response.content, 'lxml-xml')

        links = []
        for item in soup.find_all('item'):
            description = item.find('description')
            if description:
                desc_soup = BeautifulSoup(description.text, 'html.parser')
                for a_tag in desc_soup.find_all('a', href=True):
                    links.append(a_tag['href'])

        return links

    except requests.exceptions.RequestException as e:
        print(f"Error fetching the RSS feed: {e}")
        return []


############################################

def download_webpages_concurrently(links):
    webpages = {}

    def fetch_and_store(link):
        webpage = fetch_response(link)
        if webpage is None:
            print(f"Request for {link} timed out")
            return link, None
        # print(f"Content of {link} downloaded successfully")
        return link, webpage

    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_to_link = {executor.submit(fetch_and_store, link): link for link in links}
        for future in concurrent.futures.as_completed(future_to_link):
            link, webpage = future.result()
            if webpage is not None:
                webpages[link] = webpage

    print(len(webpages))
    return webpages


#########################################

def download_webpages_sequentially(links):
    webpages = {}
    for link in links:
        webpage = fetch_response(link)
        if webpage is None:     # if the request times out it returns "None"
            print(f"Request for {link} timed out")
            continue
        # print(f"Content of {link} downloaded successfully")
        webpages[link] = webpage

    print(len(webpages))
    return webpages


def extract_text(webpages):
    extracted_text = {}
    extracted_metadata = {}
    for link, webpage in webpages.items():
        text = extract(webpage, include_tables=False, include_comments=False, favor_recall=True, with_metadata=False)
        if text:
            extracted_text[link] = text
        else:
            metadata = extract(webpage, with_metadata=True)
            extracted_metadata[link] = metadata

    return extracted_text, extracted_metadata











