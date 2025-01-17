import requests
from bs4 import BeautifulSoup
import time

rss_url = "https://mstdn.social/@pinboard_pop.rss"


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



def fetch_html_from_links(links):
    html_contents = {}

    for link in links:
        try:
            response = requests.get(link)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            html_contents[link] = soup.prettify()
            # time.sleep(2)

        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch {link}: {e}")

    return html_contents




links = extract_links_from_rss(rss_url)
for link in links:
    print(link)
print("Amount of links: " + str(len(links)))

html_contents = fetch_html_from_links(links)
print("---------------------------")

first_link, first_content = next(iter(html_contents.items()))
print(f"HTML content from {first_link} (first 1000 characters):\n{first_content[:1000]}...")

print("---------------------------")
print("Amount of html pages: "+ str(len(html_contents)))