"""Dieses Modul dient dazu, die Popularität eines Artikels auf Hacker News zu ermitteln.
Dazu wird die Algolia-API von Hacker News abgefragt, welche Stories auf Hacker News anhand der URL durchsucht.
Die Funktion gibt die Anzahl der Points für die gefundene Story zurück,
oder None, falls keine Ergebnisse gefunden werden oder ein Fehler auftritt."""

# package imports
import requests

#Imports eigener Funktionen
from .logger import logger

""" Die Function ruft die Anzahl der Punkte eines Artikels auf Hacker News ab. Als Parameter wird die URL des gesuchten Artikels übergeben.
Als maximale Wartezeit für die Anfrage können optional Sekunden angegeben werden. """

def fetch_hn_points(url: str, timeout=8):
    try:
        logger.debug(f"Abrufen der Hacker-News-Punkte für URL: {url} mit Timeout={timeout}")

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
            logger.info(f"Keine Ergebnisse gefunden für URL: {url}")
            return None

        best = max(hits, key=lambda x: (x.get("points") or 0))
        points = best.get("points") or 0
        logger.info(f"Gefundene Story mit {points} Punkten für URL: {url}")

        return points
    except requests.exceptions.Timeout:
        logger.warning(f"Zeitüberschreitung nach {timeout} Sekunden für URL: {url}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Anfrage fehlgeschlagen für URL {url}: {e}")
        return None
    except Exception as e:
        logger.error(f"Unerwarteter Fehler beim Abrufen der HN-Punkte für {url}: {e}")
        return None
