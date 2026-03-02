"""Cloud Function zur Erzeugung und Versendung des täglichen Reports.

Diese Funktion ist bewusst eigenständig von der bisherigen
`rss_mail_summarizer/main.py` getrennt, damit sie einzeln deployed
werden kann. Sie liest nicht gesendete Einträge aus der Firestore‑Datenbank,
bildet optional mit Hilfe der bereits vorhandenen LLM‑Funktionen
Summaries (falls noch keine vorhanden sind) und versendet die
Ergebnisse per Gmail API.

In der GCP‑Konfiguration wird der Entry‑Point auf
`sendmail_trigger` gesetzt; die Funktion wird vom Scheduler oder per HTTP
angestossen.
"""

import os
import logging
from dotenv import load_dotenv
import functions_framework

# interne helpers
from database import get_unsent_entries, mark_as_sent, add_datarecord
from helpers import gmail_send_mail, create_markdown_report, AIService, get_gemini_api_key

# Logger setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


load_dotenv()

# Umgebungskonstanten (werden auch im Service genutzt)
MARKDOWN_REPORT_PATH = "markdown_report.md"
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")
PROJECT_ID = os.environ.get("PROJECT_ID")

# die constants werden jetzt in utils verwaltet


class SendMailService:
    """Einfache Orchestrierungs-Klasse, die Helfermodule zusammenführt.

    Die früher monolithische Implementierung existiert nun in mehreren
    Dateien (`gmail_utils`, `llm_helpers`, `report`, `utils`). Die Klasse
    selbst übernimmt nur die Konfiguration und den Workflow.
    """

    def __init__(self, sender_email: str, recipient_email: str):
        self.sender_email = sender_email
        self.recipient_email = recipient_email
        self.gemini_api_key = get_gemini_api_key()
        self.ai = AIService(self.gemini_api_key)

    # ---- Core workflow ----
    def run(self):
        unsent = get_unsent_entries()
        if not unsent:
            logger.info("Keine ungesendeten Einträge gefunden.")
            return False

        urls_without_summary = []
        for e in unsent:
            summary = e.get("summary")
            if not summary or not str(summary).strip() or str(summary).strip().lower() in ["n/a", "none", "null"]:
                urls_without_summary.append(e["url"])

        logger.debug("URLs ohne gültige Summary: %s", urls_without_summary)
        if urls_without_summary:
            youtube_urls = [u for u in urls_without_summary if "youtube.com" in u or "youtu.be" in u]
            web_urls = [u for u in urls_without_summary if u not in youtube_urls]
            summaries = {}
            if web_urls:
                summaries.update(self.ai.summarise_and_categorize_websites(web_urls))
            if youtube_urls:
                summaries.update(self.ai.summarise_youtube_videos(youtube_urls))
            for url, meta in summaries.items():
                add_datarecord(
                    url=url,
                    category=meta.get("category"),
                    summary=meta.get("summary"),
                    subcategory=meta.get("subcategory", None),
                    reading_time=meta.get("reading_time"),
                    hn_points=meta.get("hn_points"),
                    mail_sent=False,
                )

        summaries_from_db = {
            entry["url"]: {
                "category": entry.get("category"),
                "subcategory": entry.get("subcategory"),
                "summary": entry.get("summary"),
                "reading_time": entry.get("reading_time"),
                "hn_points": entry.get("hn_points"),
                "alert": entry.get("alert", False),
            }
            for entry in unsent
        }

        create_markdown_report(summaries_from_db, MARKDOWN_REPORT_PATH)
        gmail_send_mail(
            self.sender_email,
            self.recipient_email,
            subject="Today's News",
            mail_body_file=MARKDOWN_REPORT_PATH,
        )
        mark_as_sent(unsent)
        logger.info("Mailversand abgeschlossen.")
        return True



@functions_framework.http

def sendmail_trigger(request=None):
    """HTTP‑Entry‑Point, der einen `SendMailService` ausführt."""
    try:
        service = SendMailService(sender_email=SENDER_EMAIL, recipient_email=RECIPIENT_EMAIL)
        ok = service.run()
        return ("mail sent", 200) if ok else ("no entries", 200)
    except Exception as e:
        logger.error("Fehler in sendmail_trigger: %s", e, exc_info=True)
        return (f"error: {e}", 500)
