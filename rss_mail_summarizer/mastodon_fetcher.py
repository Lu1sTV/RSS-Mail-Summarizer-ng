import os
import time
from mastodon import Mastodon
from bs4 import BeautifulSoup

MASTODON_INSTANCE_URL = "https://mstdn.social"
TARGET_USERNAME = "pinboard_pop"
STATE_FILE = "last_toot_id.txt"


def get_links_via_mastodon_api():
    start_time = time.time()

    mastodon = Mastodon(api_base_url=MASTODON_INSTANCE_URL)

    try:
        account = mastodon.account_lookup(f"{TARGET_USERNAME}@mstdn.social")

        if not account:
            print(f"Fehler: Benutzer {TARGET_USERNAME} nicht gefunden.")
            return []

        user_id = account['id']

        # Letzte bekannte Toot-ID
        since_id = None
        if os.path.exists(STATE_FILE):
            with open(STATE_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    since_id = content

        # Beiträge laden
        toots = mastodon.account_statuses(user_id, since_id=since_id, limit=20)

        if not toots:
            print("Keine neuen Toots seit dem letzten Durchlauf gefunden.")
            return []

        latest_toot_id = toots[0]['id']
        with open(STATE_FILE, 'w') as f:
            f.write(str(latest_toot_id))

        # Links extrahieren
        extracted_links = []
        for toot in toots:
            soup = BeautifulSoup(toot['content'], 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if MASTODON_INSTANCE_URL not in href and "hashtag" not in a_tag.get('rel', []) and "mention" not in a_tag.get('class', []):
                    extracted_links.append(href)

        print(f"{len(extracted_links)} neue Links via Mastodon API gefunden.")
        return extracted_links

    except Exception as e:
        print(f"Ein Fehler bei der Kommunikation mit der Mastodon-API ist aufgetreten: {e}")
        return []

    finally:
        duration = time.time() - start_time
        print(f"Funktion 'get_links_via_mastodon_api' dauerte {duration:.2f} Sekunden.")
