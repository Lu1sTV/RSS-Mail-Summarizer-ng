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
from datetime import date

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
        
        if not self.gemini_api_key:
            logger.error("❌ KRITISCH: Kein gültiger Gemini API-Key gefunden! Überprüfe:")
            logger.error("   - Umgebungsvariable GEMINI_API_KEY")
            logger.error("   - Secret Manager 'gemini-api-key' ")
            logger.error("   - Fallback RSS_VERTEX_AI_KEY")
            raise RuntimeError("Kein Gemini API-Key konfiguriert. Cloud Function kann nicht starten.")
        
        logger.info("✓ Gemini API-Key erfolgreich geladen")
        self.ai = AIService(self.gemini_api_key)

    # ---- Core workflow ----
    def run(self):
        unsent = get_unsent_entries()
        if not unsent:
            logger.info("Keine ungesendeten Einträge gefunden.")
            return False

        logger.info(f"Gefundene ungesendete Einträge: {len(unsent)}")

        urls_without_summary = []
        for e in unsent:
            summary = e.get("summary")
            if not summary or not str(summary).strip() or str(summary).strip().lower() in ["n/a", "none", "null"]:
                urls_without_summary.append(e["url"])

        logger.info(f"URLs ohne gültige Summary: {len(urls_without_summary)}")
        logger.debug("URLs ohne Summary: %s", urls_without_summary)

        if urls_without_summary:
            youtube_urls = [u for u in urls_without_summary if "youtube.com" in u or "youtu.be" in u]
            web_urls = [u for u in urls_without_summary if u not in youtube_urls]
            
            logger.info(f"Web-URLs zu verarbeiten: {len(web_urls)}, YouTube-URLs: {len(youtube_urls)}")
            
            summaries = {}
            
            if web_urls:
                try:
                    logger.info(f"Rufe summarise_and_categorize_websites mit {len(web_urls)} URLs auf...")
                    web_results = self.ai.summarise_and_categorize_websites(web_urls)
                    logger.info(f"summarise_and_categorize_websites returned {len(web_results)} results")
                    summaries.update(web_results)
                except Exception as e:
                    logger.error(f"Fehler bei summarise_and_categorize_websites: {e}", exc_info=True)
                    raise
            
            if youtube_urls:
                try:
                    logger.info(f"Rufe summarise_youtube_videos mit {len(youtube_urls)} URLs auf...")
                    youtube_results = self.ai.summarise_youtube_videos(youtube_urls)
                    logger.info(f"summarise_youtube_videos returned {len(youtube_results)} results")
                    summaries.update(youtube_results)
                except Exception as e:
                    logger.error(f"Fehler bei summarise_youtube_videos: {e}", exc_info=True)
                    raise
            
            logger.info(f"Gesamt Summaries erhalten: {len(summaries)}")
            for url, meta in summaries.items():
                logger.debug(f"Schreibe Summary für {url}: category={meta.get('category')}, summary={str(meta.get('summary'))[:50]}...")
                add_datarecord(
                    url=url,
                    category=meta.get("category"),
                    summary=meta.get("summary"),
                    subcategory=meta.get("subcategory", None),
                    reading_time=meta.get("reading_time"),
                    hn_points=meta.get("hn_points"),
                    mail_sent=False,
                )
            
            # 🔑 KRITISCH: Nach LLM-Aufrufen DB nochmal laden, um die neuen Summaries zu holen!
            logger.info("Lade aktualisierte Einträge aus DB...")
            unsent = get_unsent_entries()
            logger.info(f"Aktualisierte Einträge geladen: {len(unsent)}")

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

        today_str = date.today()

        create_markdown_report(summaries_from_db, MARKDOWN_REPORT_PATH)
        gmail_send_mail(
            self.sender_email,
            self.recipient_email,
            subject=f"Today's News ({today_str})",
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
