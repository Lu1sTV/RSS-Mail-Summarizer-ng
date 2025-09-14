"""Dieses Modul dient dazu, die Popularität eines Artikels auf Hacker News zu ermitteln.
Dazu wird die Algolia-API von Hacker News abgefragt, welche Stories auf Hacker News anhand der URL durchsucht.
Die Funktion gibt die Anzahl der Points für die gefundene Story zurück,
oder None, falls keine Ergebnisse gefunden werden oder ein Fehler auftritt."""

import os
import logging
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get LOG_LEVEL from .env, default to INFO if not set
log_level = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure logging
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)


""" Die Function ruft die Anzahl der Punkte eines Artikels auf Hacker News ab. Als Parameter wird die URL des gesuchten Artikels übergeben.
Als maximale Wartezeit für die Anfrage können optional Sekunden angegeben werden. """

def fetch_hn_points(url: str, timeout=8):
    try:
        logger.debug(f"Fetching Hacker News points for URL: {url} with timeout={timeout}")
        
        r = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={
                "query": url,
                "restrictSearchableAttributes": "url",
                "tags": "story",
            },
            timeout=timeout,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        
        if not hits:
            logger.info(f"No results found for URL: {url}")
            return None
        
        best = max(hits, key=lambda x: (x.get("points") or 0))
        points = best.get("points") or 0
        logger.info(f"Found story with {points} points for URL: {url}")
        
        return points
    except requests.exceptions.Timeout:
        logger.warning(f"Timeout after {timeout} seconds for URL: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed for URL {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error while fetching HN points for {url}: {e}")
        return None
