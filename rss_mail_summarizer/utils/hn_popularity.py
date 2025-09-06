""" Dieses Modul dient dazu, die Popularität eines Artikels auf Hacker News zu ermitteln. 
Dazu wird die Algolia-API von Hacker News abgefragt, welche Stories auf Hacker News anhand der URL durchsucht. 
Die Funktion gibt die Anzahl der Points für die gefundene Story zurück, 
oder None, falls keine Ergebnisse gefunden werden oder ein Fehler auftritt. """

import requests

""" Die Function ruft die Anzahl der Punkte eines Artikels auf Hacker News ab. Als Parameter wird die URL des gesuchten Artikels übergeben.
Als maximale Wartezeit für die Anfrage können optional Sekunden angegeben werden. """
def fetch_hn_points(url: str, timeout=8):
    try:
        # Sendet GET-Anfrage an die Algolia-API
        r = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": url, "restrictSearchableAttributes": "url", "tags": "story"},
            timeout=timeout,
        )
        r.raise_for_status()
        # Extrahiert die Treffer und findet den Eintrag mit den meisten Punkten
        hits = r.json().get("hits", [])
        if not hits:
            return None
        best = max(hits, key=lambda x: (x.get("points") or 0))
        return best.get("points") or 0
    except Exception:
        return None