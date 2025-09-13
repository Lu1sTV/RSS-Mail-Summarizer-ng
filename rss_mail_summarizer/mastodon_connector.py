"""
Das Skript holt neue Beiträge vom definierten Mastodon-Feed ab
und extrahiert Links aus deren Inhalt.
Die gefundenen Links werden in der Firestore-Datenbank gespeichert.
Um doppelte Verarbeitung zu vermeiden, wird die zuletzt verarbeitete Toot-ID
in einer Datei gespeichert und beim nächsten Lauf wiederverwendet.
"""

#package Imports
from mastodon import Mastodon
from bs4 import BeautifulSoup
import os
import time

#Imports eigener Funktionen
from database import add_url_to_website_collection, get_last_toot_id, save_last_toot_id


MASTODON_INSTANCE_URL = "https://mstdn.social"
TARGET_USERNAME = "pinboard_pop"
#STATE_FILE = "last_toot_id.txt"


# Holt neue Toots vom definierten Mastodon-Account und speichert enthaltene Links in der Datenbank
def fetch_and_store_mastodon_links():
    start_time = time.time()
    print("-- starting mastodon connector")
    mastodon = Mastodon(api_base_url=MASTODON_INSTANCE_URL)

    try:
        # Account anhand Username suchen
        account = mastodon.account_lookup(f"{TARGET_USERNAME}@mstdn.social")
        if not account:
            print(f"Fehler: Benutzer {TARGET_USERNAME} nicht gefunden.")
            return

        user_id = account["id"]
        new_links = []

        # Prüfen, ob es bereits eine im Firestore gespeicherte letzte Toot-ID gibt
        since_id = get_last_toot_id()
        if since_id:
            print(f"Lade neue Toots seit ID {since_id} ...")
        else:
            print("Erster Lauf: 20 neueste Toots werden geladen.")

        # Erste Abfrage von Toots (max. 20)
        toots = mastodon.account_statuses(user_id, limit=20, since_id=since_id)
        all_toots = list(toots)

        # Weitere Seiten abrufen, bis keine neuen Toots mehr vorhanden sind
        # Nur Toots berücksichtigen, die neuer sind als since_id
        # Und beim ersten Aufruf nicht paginieren, sondern nur die neuesten 20 holen
        if since_id:
            while True:
                next_page = mastodon.fetch_next(toots)
                if not next_page:
                    break

                filtered = [t for t in next_page if int(t["id"]) > int(since_id)]
                if not filtered:
                    break

                all_toots.extend(filtered)
                toots = next_page

        if not all_toots:
            print("Keine neuen Toots gefunden.")
            return

        latest_toot_id = max(int(toot["id"]) for toot in all_toots)
        save_last_toot_id(latest_toot_id)

        # Neue Toots verarbeiten und Links extrahieren
        for toot in all_toots:
            soup = BeautifulSoup(toot["content"], "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if (
                    MASTODON_INSTANCE_URL not in href
                    and "hashtag" not in a_tag.get("rel", [])
                    and "mention" not in a_tag.get("class", [])
                ):
                    add_url_to_website_collection(href)
                    new_links.append(href)

        print(f"{len(new_links)} neue Links gespeichert.")

    except Exception as e:
        print(f"Fehler bei Mastodon-Abruf: {e}")

    finally:
        duration = time.time() - start_time
        print(f"-- mastodon-connector dauerte {duration:.2f} Sekunden.")


if __name__ == "__main__":
    fetch_and_store_mastodon_links()
