"""
MastodonService

Holt neue Beiträge vom definierten Mastodon-Feed ab,
extrahiert Links aus deren Inhalt und speichert diese in der Firestore-Datenbank.
Um doppelte Verarbeitung zu vermeiden, wird die zuletzt verarbeitete Toot-ID
in Firestore gespeichert und beim nächsten Lauf wiederverwendet.
"""

import time
from urllib.parse import urlparse
from mastodon import Mastodon
from bs4 import BeautifulSoup
from config import Config

# Importiere shared modules (lokal + Cloud)
from database import FirestoreRepository, logger


class MastodonService:
    """Service für die Verwaltung von Mastodon-Links"""
    
    def __init__(self):
        """Initialisiert den Mastodon-Service"""
        self.instance_url = Config.INSTANCE_URL
        self.target_username = Config.TARGET_USERNAME
        self.entry_limit = Config.ENTRY_LIMIT
        self.fetch_all_since_last = getattr(Config, "FETCH_ALL_SINCE_LAST", True)

        self.mastodon = Mastodon(api_base_url=self.instance_url)
        self.repo = FirestoreRepository()

    def _fetch_mode(self) -> str:
        return "FULL_SYNC" if self.fetch_all_since_last else "LIMITED_SYNC"
    
    def fetch_and_store_links(self):
        """
        Holt neue Toots vom definierten Mastodon-Account
        und speichert enthaltene Links in der Datenbank.
        """
        start_time = time.time()
        mode = self._fetch_mode()
        logger.info(
            f"Starte Mastodon-Connector [mode={mode}] (limit={self.entry_limit}, fetch_all_since_last={self.fetch_all_since_last})..."
        )

        try:
            # Account anhand Username suchen
            account_domain = urlparse(self.instance_url).netloc
            account = self.mastodon.account_lookup(f"{self.target_username}@{account_domain}")
            if not account:
                logger.error(f"Benutzer {self.target_username} nicht gefunden.")
                return

            user_id = account["id"]
            new_links = []

            # Prüfen, ob es bereits eine gespeicherte letzte Toot-ID gibt
            since_id = self.repo.get_last_toot_id()
            if since_id:
                if self.fetch_all_since_last:
                    logger.info(f"[mode={mode}] Branch aktiv: alle neuen Toots seit ID {since_id} laden.")
                else:
                    logger.info(
                        f"[mode={mode}] Branch aktiv: maximal {self.entry_limit} neue Toots seit ID {since_id} laden."
                    )
            else:
                logger.info(f"[mode={mode}] Erster Lauf: bis zu {self.entry_limit} neueste Toots werden geladen.")

            # Erste Abfrage von Toots (max. entry_limit)
            toots = self.mastodon.account_statuses(user_id, limit=self.entry_limit, since_id=since_id)
            all_toots = list(toots)
            logger.info(f"[mode={mode}] Initiale API-Antwort: {len(all_toots)} Toots.")

            # Weitere Seiten abrufen nur im Modus "alle seit letztem Crawl"
            if since_id and self.fetch_all_since_last:
                while True:
                    next_page = self.mastodon.fetch_next(toots)
                    if not next_page:
                        break

                    filtered = [t for t in next_page if int(t["id"]) > int(since_id)]
                    if not filtered:
                        break

                    all_toots.extend(filtered)
                    toots = next_page

                    logger.info(f"[mode={mode}] Gesamtzahl zu verarbeitender Toots: {len(all_toots)}")

            if not all_toots:
                logger.info("Keine neuen Toots gefunden.")
                return

            latest_toot_id = max(int(toot["id"]) for toot in all_toots)
            self.repo.save_last_toot_id(latest_toot_id)
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
        Extrahiert Links aus Toots und speichert sie zusammen mit 
        Mastodon-Metadaten in der Datenbank.
        
        Args:
            toots: Liste der Toots zum Verarbeiten
            
        Returns:
            Liste der neuen Links
        """
        new_links = []
        
        for toot in toots:
            # 1. Metadaten aus dem Toot-Dictionary extrahieren
            toot_url = toot.get("url")
            created_at = toot.get("created_at")
            # created_at ist oft ein datetime-Objekt, wir machen einen String daraus
            toot_date_str = created_at.strftime("%Y-%m-%d %H:%M:%S") if created_at else None

            # 2. HTML parsen
            soup = BeautifulSoup(toot["content"], "html.parser")
            
            # 3. Den reinen Text ohne HTML-Tags extrahieren (als Kontext für später)
            clean_text = soup.get_text(separator=" ", strip=True)

            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"]
                if (
                    self.instance_url not in href
                    and "hashtag" not in a_tag.get("rel", [])
                    and "mention" not in a_tag.get("class", [])
                ):
                    # 4. URL UND die Metadaten an die Datenbank übergeben
                    self.repo.add_url_to_website_collection(
                        url=href,
                        toot_text=clean_text,
                        toot_url=toot_url,
                        toot_date=toot_date_str
                    )
                    new_links.append(href)
        
        return new_links