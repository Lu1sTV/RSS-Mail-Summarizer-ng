"""
Mastodon Connector Cloud Function

Entry-Point für Google Cloud Functions.
Ruft über den Mastodon-Connector Links ab und speichert diese in der Datenbank.
"""

import json
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
        Tuple[str, int]: (JSON response, HTTP status code)
    """
    try:
        logger.debug("Starte Mastodon-Connector...")
        service = MastodonService()
        telemetry = service.fetch_and_store_links()
        logger.info("Mastodon-Connector erfolgreich ausgeführt.")

        response_data = {
            "status": "success",
            "resource": telemetry["resource"],
            "details": {
                "entries_processed": telemetry["entries_processed"],
                "links_stored": telemetry["links_stored"],
                "feeds_total": telemetry["feeds_total"],
                "feeds_processed": telemetry["feeds_processed"],
                "feeds_failed": telemetry["feeds_failed"],
                "duration_seconds": telemetry["duration_seconds"],
                "mode": telemetry["mode"],
            },
        }
        return json.dumps(response_data, indent=2), 200
    except Exception as e:
        logger.error(f"Fehler in mastodon_connector_activate(): {e}")
        return json.dumps({
            "status": "error",
            "resource": "website",
            "details": {
                "entries_processed": 0,
                "error": str(e),
            },
        }, indent=2), 500
