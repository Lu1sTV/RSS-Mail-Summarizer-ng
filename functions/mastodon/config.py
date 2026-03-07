import os

class Config:
    """Zentrale Konfiguration – alle Einstellungen an einem Ort"""
    
    # Mastodon Einstellungen
    INSTANCE_URL = "https://mstdn.social"
    TARGET_USERNAME = "pinboard_pop"
    
    # Limit der mastodon Einträge
    ENTRY_LIMIT = 20 

    # True: alle neuen Einträge seit letztem Crawl holen (mit Pagination)
    # False: maximal ENTRY_LIMIT neue Einträge seit letztem Crawl holen
    FETCH_ALL_SINCE_LAST = True
    
    # Projekt-Metadaten
    PROJECT_ID = os.environ.get('PROJECT_ID', 'mail-summerizer-486619')
    LOG_LEVEL = "INFO"
