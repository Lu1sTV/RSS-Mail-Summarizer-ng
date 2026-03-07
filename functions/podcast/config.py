"""
Podcast Generator – Konfiguration
"""

import os


class PodcastConfig:
    """Zentrale Config für den Podcast-Generator."""

    # Quellen-Filter – ["*"] = alle, [] = deaktiviert
    SOURCES = {
        "mastodon": ["*"],
        "alerts": ["*"],
        "rss": [],
    }

    # Max. Anzahl Links über alle Quellen
    LIMIT = 20

    # Nur Einträge der letzten X Stunden (None = kein Limit)
    TIME_WINDOW_HOURS = None

    # GCS Bucket für die fertige MP3
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")
