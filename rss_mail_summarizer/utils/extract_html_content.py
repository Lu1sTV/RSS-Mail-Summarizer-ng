import requests
from bs4 import BeautifulSoup


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
