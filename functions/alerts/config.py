"""
Gmail Alerts Processor – Konfiguration
"""

from typing import List, Dict, Optional


class AlertConfig:
    """Zentrale Config für den Alerts Processor."""

    # Alert-Label Definitionen
    ALERT_CONFIG: List[Dict[str, str]] = [
        {"name": "Carlo Masala", "label": "alerts-carlo-masala", "processed_label": "alerts-carlo-masala-processed"},
    ]

    # URLs die ignoriert werden
    LINK_BLACKLIST: List[str] = [
        "google.com/alerts", "alerts/remove", "alerts/edit",
        "support.google.com", "google.com/settings",
    ]

    # Gmail API Scopes
    SCOPES: List[str] = ["https://www.googleapis.com/auth/gmail.modify"]

    # Max. Nachrichten pro Label-Abruf (None = Gmail default)
    MAX_RESULTS: Optional[int] = 50

    # Nur Mails der letzten X Tage (None = kein Limit)
    MAX_AGE_DAYS: Optional[int] = None
