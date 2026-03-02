import functions_framework
import requests
import google.auth.transport.requests
import google.oauth2.id_token
import logging
import os

# URLs deiner bereits deployten Funktionen
MASTODON_URL = os.environ.get("MASTODON_URL")
ALERTS_URL = os.environ.get("ALERTS_URL")
SENDMAIL_URL = os.environ.get("SENDMAIL_URL")

def get_id_token(url):
    """Erzeugt ein OIDC-Token für die Authentifizierung zwischen Functions."""
    auth_req = google.auth.transport.requests.Request()
    return google.oauth2.id_token.fetch_id_token(auth_req, url)

@functions_framework.http
def orchestrate_pipeline(request):
    logging.info("Starte Pipeline...")
    
    for url in [MASTODON_URL, ALERTS_URL, SENDMAIL_URL]:
        try:
            token = get_id_token(url)
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(url, headers=headers, timeout=300)
            logging.info(f"Aufruf von {url} Status: {response.status_code}")
            response.raise_for_status()
        except Exception as e:
            logging.error(f"Fehler bei {url}: {e}")
            return f"Fehler in der Kette: {e}", 500
            
    return "Pipeline erfolgreich durchgelaufen", 200