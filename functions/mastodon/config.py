import os
from typing import List, Dict


class Config:
    """Zentrale Konfiguration – alle Einstellungen an einem Ort"""

    # Mastodon Feed-Definitionen
    MASTODON_FEEDS: List[Dict[str, str]] = [
        {"name": "pinboard_pop", "instance": "https://mstdn.social", "username": "pinboard_pop"},
    ]

    # Limit der mastodon Einträge pro Feed
    ENTRY_LIMIT = 10

    # True: alle neuen Einträge seit letztem Crawl holen (mit Pagination)
    # False: maximal ENTRY_LIMIT neue Einträge seit letztem Crawl holen
    FETCH_ALL_SINCE_LAST = True

    # Laufzeit-Metadaten
    LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
