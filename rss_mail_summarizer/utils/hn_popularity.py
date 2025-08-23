import requests

def fetch_hn_points(url: str, timeout=8):
    try:
        r = requests.get(
            "https://hn.algolia.com/api/v1/search",
            params={"query": url, "restrictSearchableAttributes": "url", "tags": "story"},
            timeout=timeout,
        )
        r.raise_for_status()
        hits = r.json().get("hits", [])
        if not hits:
            return None
        best = max(hits, key=lambda x: (x.get("points") or 0))
        return best.get("points") or 0
    except Exception:
        return None