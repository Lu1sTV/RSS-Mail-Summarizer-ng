import requests
from bs4 import BeautifulSoup
from trafilatura import fetch_url, extract


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


def download_webpages(links):
    webpages = {}
    for link in links:
        webpage = fetch_url(link)
        if webpage is None:
            print(f"Request for {link} timed out")
            continue
        webpages[link] = webpage

    return webpages


def extract_text(webpages):
    extracted_text = {}
    extracted_metadata = {}
    for link, webpage in webpages.items():
        text = extract(webpage, include_tables=False, include_comments=False, favor_recall=True, with_metadata=True)
        if text:
            extracted_text[link] = text
        else:
            metadata = extract(webpage, with_metadata=True)
            extracted_metadata[link] = metadata

    return extracted_text, extracted_metadata












