"""
Das Skript holt neue Beiträge vom definierten Mastodon-Feed ab
und extrahiert Links aus deren Inhalt.
Die gefundenen Links werden in der Firestore-Datenbank gespeichert.
Um doppelte Verarbeitung zu vermeiden, wird die zuletzt verarbeitete Toot-ID
in einer Datei gespeichert und beim nächsten Lauf wiederverwendet.
"""

# package Imports
from mastodon import Mastodon
from bs4 import BeautifulSoup
import os
import time
import logging

# Imports eigener Funktionen
from database import add_url_to_website_collection, get_last_toot_id, save_last_toot_id


# Logging-Konfiguration
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)


MASTODON_INSTANCE_URL = "https://mstdn.social"
TARGET_USERNAME = "pinboard_pop"


# Holt neue Toots vom definierten Mastodon-Account und speichert enthaltene Links in der Datenbank
def fetch_and_store_mastodon_links():
    start_time = time.time()
    logger.info("Starte Mastodon-Connector...")

    mastodon = Mastodon(api_base_url=MASTODON_INSTANCE_URL)

    try:
        # Account anhand Username suchen
        account = mastodon.account_lookup(f"{TARGET_USERNAME}@mstdn.social")
        if not account:
            logger.error(f"Benutzer {TARGET_USERNAME} nicht gefunden.")
            return

        user_id = account["id"]
        new_links = []

        # Prüfen, ob es bereits eine gespeicherte letzte Toot-ID gibt
        since_id = get_last_toot_id()
        if since_id:
            logger.info(f"Lade neue Toots seit ID {since_id} ...")
        else:
            logger.info("Erster Lauf: 20 neueste Toots werden geladen.")

        # Erste Abfrage von Toots (max. 20)
        toots = mastodon.account_statuses(user_id, limit=20, since_id=since_id)
        all_toots = list(toots)

        # Weitere Seiten abrufen, nur wenn since_id gesetzt ist
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
            logger.info("Keine neuen Toots gefunden.")
            return

        latest_toot_id = max(int(toot["id"]) for toot in all_toots)
        save_last_toot_id(latest_toot_id)
        logger.info(f"Gespeicherte letzte Toot-ID: {latest_toot_id}")

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

        logger.info(f"{len(new_links)} neue Links gespeichert.")

    except Exception as e:
        logger.exception(f"Fehler bei Mastodon-Abruf: {e}")

    finally:
        duration = time.time() - start_time
        logger.info(f"Mastodon-Connector abgeschlossen in {duration:.2f} Sekunden.")


if __name__ == "__main__":
    fetch_and_store_mastodon_links()
