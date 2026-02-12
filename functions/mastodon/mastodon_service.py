"""
MastodonService

Holt neue Beiträge vom definierten Mastodon-Feed ab,
extrahiert Links aus deren Inhalt und speichert diese in der Firestore-Datenbank.
Um doppelte Verarbeitung zu vermeiden, wird die zuletzt verarbeitete Toot-ID
in Firestore gespeichert und beim nächsten Lauf wiederverwendet.
"""

import sys
import time
from pathlib import Path
from mastodon import Mastodon
from bs4 import BeautifulSoup

# Importiere shared modules (lokal + Cloud)
shared_root = Path(__file__).resolve().parents[2] / "rss_mail_summarizer"
sys.path.insert(0, str(shared_root))
from database import add_url_to_website_collection, get_last_toot_id, save_last_toot_id
from utils.logger import logger


class MastodonService:
    """Service für die Verwaltung von Mastodon-Links"""
    
    MASTODON_INSTANCE_URL = "https://mstdn.social"
    TARGET_USERNAME = "pinboard_pop"
    
    def __init__(self):
        """Initialisiert den Mastodon-Service"""
        self.mastodon = Mastodon(api_base_url=self.MASTODON_INSTANCE_URL)
    
    def fetch_and_store_links(self):
        """
        Holt neue Toots vom definierten Mastodon-Account
        und speichert enthaltene Links in der Datenbank.
        """
        start_time = time.time()
        logger.info("Starte Mastodon-Connector...")

        try:
            # Account anhand Username suchen
            account = self.mastodon.account_lookup(f"{self.TARGET_USERNAME}@mstdn.social")
            if not account:
                logger.error(f"Benutzer {self.TARGET_USERNAME} nicht gefunden.")
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
            toots = self.mastodon.account_statuses(user_id, limit=20, since_id=since_id)
            all_toots = list(toots)

            # Weitere Seiten abrufen, nur wenn since_id gesetzt ist
            if since_id:
                while True:
                    next_page = self.mastodon.fetch_next(toots)
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
            new_links = self._extract_and_store_links(all_toots)

            logger.info(f"{len(new_links)} neue Links gespeichert.")

        except Exception as e:
            logger.exception(f"Fehler bei Mastodon-Abruf: {e}")

        finally:
            duration = time.time() - start_time
            logger.info(f"Mastodon-Connector abgeschlossen in {duration:.2f} Sekunden.")
    
    def _extract_and_store_links(self, toots: list) -> list:
        """
        Extrahiert Links aus Toots und speichert sie in der Datenbank.
        
        Args:
            toots: Liste der Toots zum Verarbeiten
            
        Returns:
            Liste der neuen Links
        """
        new_links = []
        
        for toot in toots:
            soup = BeautifulSoup(toot["content"], "html.parser")
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if (
                    self.MASTODON_INSTANCE_URL not in href
                    and "hashtag" not in a_tag.get("rel", [])
                    and "mention" not in a_tag.get("class", [])
                ):
                    add_url_to_website_collection(href)
                    new_links.append(href)
        
        return new_links
