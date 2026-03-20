"""
MastodonService

Holt neue Beiträge von den definierten Mastodon-Feeds ab,
extrahiert Links aus deren Inhalt und speichert diese in der Firestore-Datenbank.
Um doppelte Verarbeitung zu vermeiden, wird die zuletzt verarbeitete Toot-ID
pro Feed in Firestore gespeichert und beim nächsten Lauf wiederverwendet.
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
        self.feeds = Config.MASTODON_FEEDS
        self.entry_limit = Config.ENTRY_LIMIT
        self.fetch_all_since_last = getattr(Config, "FETCH_ALL_SINCE_LAST", True)
        self.repo = FirestoreRepository()

    def _fetch_mode(self) -> str:
        return "FULL_SYNC" if self.fetch_all_since_last else "LIMITED_SYNC"
    
    def fetch_and_store_links(self):
        """
        Iteriert über alle konfigurierten Mastodon-Feeds
        und speichert enthaltene Links in der Datenbank.

        Returns:
            Telemetrie-Daten fuer API-Antworten und Monitoring.
        """
        start_time = time.time()
        mode = self._fetch_mode()
        total_links = 0
        total_entries_processed = 0
        feeds_processed = 0
        feeds_failed = 0

        logger.info(
            f"Starte Mastodon-Connector [mode={mode}] "
            f"(feeds={len(self.feeds)}, limit={self.entry_limit}, "
            f"fetch_all_since_last={self.fetch_all_since_last})..."
        )

        for feed in self.feeds:
            feed_name = feed["name"]
            instance_url = feed["instance"]
            username = feed["username"]

            try:
                feed_result = self._process_feed(feed_name, instance_url, username, mode)
                total_links += feed_result["links_stored"]
                total_entries_processed += feed_result["entries_processed"]
                feeds_processed += 1
            except Exception as e:
                feeds_failed += 1
                logger.exception(f"Fehler bei Feed '{feed_name}': {e}")

        duration = time.time() - start_time
        logger.info(
            f"Mastodon-Connector abgeschlossen in {duration:.2f} Sekunden. "
            f"{total_links} neue Links aus {len(self.feeds)} Feeds gespeichert."
        )

        return {
            "resource": "website",
            "entries_processed": total_entries_processed,
            "links_stored": total_links,
            "feeds_total": len(self.feeds),
            "feeds_processed": feeds_processed,
            "feeds_failed": feeds_failed,
            "duration_seconds": round(duration, 2),
            "mode": mode,
        }

    def _process_feed(self, feed_name: str, instance_url: str, username: str, mode: str) -> dict:
        """
        Verarbeitet einen einzelnen Mastodon-Feed.

        Args:
            feed_name: Name des Feeds (für DB-Zuordnung)
            instance_url: Mastodon-Instanz URL
            username: Benutzername auf der Instanz
            mode: Sync-Modus (FULL_SYNC / LIMITED_SYNC)

        Returns:
            Telemetrie zum verarbeiteten Feed
        """
        logger.info(f"[{feed_name}] Verarbeite Feed @{username} auf {instance_url}...")

        mastodon = Mastodon(api_base_url=instance_url)

        # Account anhand Username suchen
        account_domain = urlparse(instance_url).netloc
        account = mastodon.account_lookup(f"{username}@{account_domain}")
        if not account:
            logger.error(f"[{feed_name}] Benutzer {username} nicht gefunden.")
            return {"entries_processed": 0, "links_stored": 0}

        user_id = account["id"]

        # Prüfen, ob es bereits eine gespeicherte letzte Toot-ID gibt
        since_id = self.repo.get_last_toot_id(feed_name)
        if since_id:
            if self.fetch_all_since_last:
                logger.info(f"[{feed_name}][mode={mode}] Alle neuen Toots seit ID {since_id} laden.")
            else:
                logger.info(
                    f"[{feed_name}][mode={mode}] Maximal {self.entry_limit} neue Toots seit ID {since_id} laden."
                )
        else:
            logger.info(f"[{feed_name}][mode={mode}] Erster Lauf: bis zu {self.entry_limit} neueste Toots werden geladen.")

        # Erste Abfrage von Toots (max. entry_limit)
        toots = mastodon.account_statuses(user_id, limit=self.entry_limit, since_id=since_id)
        all_toots = list(toots)
        logger.info(f"[{feed_name}][mode={mode}] Initiale API-Antwort: {len(all_toots)} Toots.")

        # Weitere Seiten abrufen nur im Modus "alle seit letztem Crawl"
        if since_id and self.fetch_all_since_last:
            while True:
                next_page = mastodon.fetch_next(toots)
                if not next_page:
                    break

                filtered = [t for t in next_page if int(t["id"]) > int(since_id)]
                if not filtered:
                    break

                all_toots.extend(filtered)
                toots = next_page

                logger.info(f"[{feed_name}][mode={mode}] Gesamtzahl zu verarbeitender Toots: {len(all_toots)}")

        if not all_toots:
            logger.info(f"[{feed_name}] Keine neuen Toots gefunden.")
            return {"entries_processed": 0, "links_stored": 0}

        latest_toot_id = max(int(toot["id"]) for toot in all_toots)

        # Neue Toots verarbeiten und Links extrahieren
        new_links, error_count = self._extract_and_store_links(all_toots, feed_name, instance_url)

        logger.info(
            f"[{feed_name}] Verarbeitung abgeschlossen: toots={len(all_toots)}, "
            f"links={len(new_links)}, errors={error_count}."
        )

        if error_count > 0:
            # Cursor bleibt absichtlich unveraendert, damit fehlgeschlagene Toots erneut verarbeitet werden.
            raise RuntimeError(
                f"[{feed_name}] Verarbeitung unvollstaendig ({error_count} Fehler). "
                "Cursor wird nicht aktualisiert."
            )

        self.repo.save_last_toot_id(latest_toot_id, feed_name)
        logger.info(f"[{feed_name}] Gespeicherte letzte Toot-ID: {latest_toot_id}")
        logger.info(f"[{feed_name}] {len(new_links)} neue Links gespeichert.")
        return {
            "entries_processed": len(all_toots),
            "links_stored": len(new_links),
        }
    
    def _extract_and_store_links(self, toots: list, feed_name: str, instance_url: str) -> tuple[list, int]:
        """
        Extrahiert Links aus Toots und speichert sie in der Datenbank.
        
        Args:
            toots: Liste der Toots zum Verarbeiten
            feed_name: Name des Feeds (für DB-Zuordnung)
            instance_url: Mastodon-Instanz URL
            
        Returns:
            Tupel aus Liste der neuen Links und Anzahl aufgetretener Fehler
        """
        new_links = []
        error_count = 0
        
        for toot in toots:
            toot_id = toot.get("id", "unknown")
            try:
                soup = BeautifulSoup(toot["content"], "html.parser")

                for a_tag in soup.find_all("a", href=True):
                    href = a_tag["href"]
                    if (
                        instance_url not in href
                        and "hashtag" not in a_tag.get("rel", [])
                        and "mention" not in a_tag.get("class", [])
                    ):
                        try:
                            self.repo.add_url_to_website_collection(
                                url=href,
                                feed_name=feed_name,
                            )
                            new_links.append(href)
                        except Exception as e:
                            error_count += 1
                            logger.exception(
                                f"[{feed_name}] Fehler beim Speichern von URL aus Toot {toot_id}: {href} ({e})"
                            )
            except Exception as e:
                error_count += 1
                logger.exception(f"[{feed_name}] Fehler beim Verarbeiten von Toot {toot_id}: {e}")
        
        return new_links, error_count