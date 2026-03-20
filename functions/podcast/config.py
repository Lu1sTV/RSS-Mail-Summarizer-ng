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
        "rss": ["*"],
    }

    # Max. Anzahl Links über alle Quellen
    LIMIT = 20

    # Nur Einträge der letzten X Stunden (None = kein Limit)
    TIME_WINDOW_HOURS = None

    # GCS Bucket für die fertige MP3
    GCS_BUCKET_NAME = os.environ.get("GCS_BUCKET_NAME")

    # ── Mail ──────────────────────────────────────────────
    SENDER_EMAIL = os.environ.get("SENDER_EMAIL")
    RECIPIENT_EMAIL = os.environ.get("RECIPIENT_EMAIL")

    # ── Gemini ────────────────────────────────────────────
    GEMINI_MODEL = "gemini-2.5-flash"
    SCRIPT_TEMPERATURE = 0.7
    MAX_OUTPUT_TOKENS = 65536
    MAX_CONTENT_CHARS = 15000

    # ── TTS ───────────────────────────────────────────────
    TTS_LANGUAGE = "de-DE"
    TTS_HOST_VOICE = "de-DE-Journey-D"
    TTS_GUEST_VOICE = "de-DE-Journey-F"
    TTS_SAMPLE_RATE = 44100

    # ── Script-Validierung ────────────────────────────────
    TTS_WORDS_PER_MINUTE = 140
    MIN_PODCAST_MINUTES = 15
    MAX_PODCAST_MINUTES = 25
    MAX_SCRIPT_RETRIES = 2

    # ── Signed URL ────────────────────────────────────────
    # GCS erlaubt max. 7 Tage für V4-Signed-URLs
    SIGNED_URL_EXPIRY_DAYS = 7
