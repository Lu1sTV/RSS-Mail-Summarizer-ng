"""
Mastodon Connector Cloud Function

Entry-Point für Google Cloud Functions.
Ruft über den Mastodon-Connector Links ab und speichert diese in der Datenbank.
"""

import functions_framework

# Import shared modules (lokal + Cloud)
from database import logger
from mastodon_service import MastodonService


@functions_framework.http
def mastodon_connector_activate(request):
    """
    HTTP Entry-Point für die Mastodon-Connector Cloud Function.
    
    Args:
        request: Flask request object
        
    Returns:
        Tuple[str, int]: (response message, HTTP status code)
    """
    try:
        logger.debug("Starte Mastodon-Connector...")
        service = MastodonService()
        service.fetch_and_store_links()
        logger.info("Mastodon-Connector erfolgreich ausgeführt.")
        return "OK", 200
    except Exception as e:
        logger.error(f"Fehler in mastodon_connector_activate(): {e}")
        return f"Fehler: {e}", 500
