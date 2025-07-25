from mastodon import Mastodon
from bs4 import BeautifulSoup
import os
import time
from database import add_url_to_website_collection

MASTODON_INSTANCE_URL = "https://mstdn.social"
TARGET_USERNAME = "pinboard_pop"
STATE_FILE = "last_toot_id.txt"

def fetch_and_store_mastodon_links():
    start_time = time.time()
    mastodon = Mastodon(api_base_url=MASTODON_INSTANCE_URL)

    try:
        account = mastodon.account_lookup(f"{TARGET_USERNAME}@mstdn.social")
        if not account:
            print(f"Fehler: Benutzer {TARGET_USERNAME} nicht gefunden.")
            return

        user_id = account['id']
        new_links = []

        if not os.path.exists(STATE_FILE):
            # ⇨ Erster Lauf: genau 20 Toots
            print("Erster Lauf: 20 neueste Toots werden geladen.")
            toots = mastodon.account_statuses(user_id, limit=20)
        else:
            # ⇨ Folge-Läufe: alle neuen Toots seit since_id
            with open(STATE_FILE, 'r') as f:
                since_id = f.read().strip()
            print(f"Lade neue Toots seit ID {since_id} ...")

            toots = mastodon.account_statuses(user_id, since_id=since_id, limit=20)
            all_toots = list(toots)

            # Pagination: weitere Seiten holen
            while toots and mastodon.fetch_next(toots):
                toots = mastodon.fetch_next(toots)
                all_toots.extend(toots)
            toots = all_toots

        if not toots:
            print("Keine neuen Toots gefunden.")
            return

        # Neuste Toot-ID speichern
        latest_toot_id = max(int(toot['id']) for toot in toots)
        with open(STATE_FILE, 'w') as f:
            f.write(str(latest_toot_id))

        for toot in toots:
            soup = BeautifulSoup(toot['content'], 'html.parser')
            for a_tag in soup.find_all('a', href=True):
                href = a_tag['href']
                if MASTODON_INSTANCE_URL not in href and "hashtag" not in a_tag.get('rel', []) and "mention" not in a_tag.get('class', []):
                    add_url_to_website_collection(href)
                    new_links.append(href)

        print(f"{len(new_links)} neue Links gespeichert.")

    except Exception as e:
        print(f"Fehler bei Mastodon-Abruf: {e}")

    finally:
        duration = time.time() - start_time
        print(f"Mastodon-Connector dauerte {duration:.2f} Sekunden.")

fetch_and_store_mastodon_links()
