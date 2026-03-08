"""
Sendmail Generator – Konfiguration
"""

import os

class SendmailConfig:
    """Zentrale Config für den Sendmail-Generator."""

    # Quellen-Filter – ["*"] = alle, [] = deaktiviert
    SOURCES = {
        "mastodon": ["*"],
        "alerts": ["*"],
        "rss": [],
    }

    # Max. Anzahl Links über alle Quellen
    LIMIT = 1

    # Nur Einträge der letzten X Stunden (None = kein Limit)
    TIME_WINDOW_HOURS = None