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
            response = requests.get(link, timeout=10)   # connection dauert manchmal für immer (Timer einbauen)
            response.raise_for_status()

            soup = BeautifulSoup(response.content, 'html.parser')

            html_contents[link] = soup.prettify()
            # time.sleep(2)

        except requests.exceptions.Timeout:
            print(f"Skipped {link}: request timed out after 10 seconds")
        except requests.exceptions.RequestException as e:
            print(f"Failed to fetch {link}: {e}")

    return html_contents


def clean_html(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')

    '''
    Da nur der "Hauptartikel" relevant ist müssen die restlichen Strings gefiltert werden
    Beispielsweise Kommentare, Buttons mit Text, Navigationsleisten, etc.
    Da der Aufbau jeder Seite unterschiedlich ist (verschiedene Klassennamen, etc.) ist dies nur zum Teil und unter gewissen Annahmen möglich
    Es können nicht einfach alle Links gefiltert werden, da manchmal Schlüsselwörter als Links im Text stehen (siehe Wikipedia)
    
    To Do: Verschiedene HTML Seiten analysieren und herausfinden, welche Klassen, IDs und Tags für ein gutes Ergebnis gefiltert werden müssen
    '''
    # Remove <script> and <style> tags from the HTML
    for script_or_style in soup(['script', 'style']):
        script_or_style.extract()

    # Remove unwanted elements by their tag name
    for unwanted in soup(['aside', 'footer', 'header', 'nav']):
        unwanted.extract()

    # Remove unwanted elements by class or ID
    for unwanted in soup.find_all(class_=['advertisement', 'comments', 'sponsored']):
        unwanted.extract()

    for unwanted in soup.find_all(id=['ad', 'comments', 'sponsored']):
        unwanted.extract()

    # Extract all strings
    strings = []
    for string in soup.stripped_strings:
        strings.append(string)

    return strings




links = extract_links_from_rss(rss_url)
for link in links:
    print(link)
print("Amount of links: " + str(len(links)))

html_contents = fetch_html_from_links(links)
print("---------------------------")


cleaned_html_contents = {}
for link, html in html_contents.items():
    cleaned_html_contents[link] = clean_html(html)

first_link, first_string_list = next(iter(cleaned_html_contents.items()))
for string in first_string_list:
    print(string)


# first_link, first_content = next(iter(html_contents.items()))
# print(f"HTML content from {first_link} (first 1000 characters):\n{first_content[:1000]}...")
#
# print("---------------------------")
# print("Amount of html pages: "+ str(len(html_contents)))


# print(first_content)


