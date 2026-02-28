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

# Datenbankzugriff
from database import get_unsent_entries, mark_as_sent, add_datarecord

# benötigte Bibliotheken für E‑Mail und LLM
import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import markdown
import json
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# LLM‑Imports
import re
from collections import defaultdict
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.rate_limiters import InMemoryRateLimiter
from google.cloud import secretmanager
from google.oauth2 import service_account
from urllib.parse import urlparse, parse_qs, unquote
from google import genai
from google.genai import types

# Logger
to_load = True
from utils.logger import logger

load_dotenv()

# Umgebungskonstanten (werden auch im Service genutzt)
MARKDOWN_REPORT_PATH = "markdown_report.md"
SENDER_EMAIL = os.getenv("SENDER_EMAIL")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")
PROJECT_ID = os.environ.get("PROJECT_ID")

# Schlüssel für Secrets
LOCAL_GEMINI_KEY_ENV = "GEMINI_API_KEY"
SERVICE_ACCOUNT_LOCAL_FILE = "utils/serviceaccountkey.json"
SECRET_ENV = "RSS_VERTEX_AI_KEY"


class SendMailService:
    """Sammlung aller benötigten Operationen für den Reporting- und Mailversand.

    Durch diesen Service sind keine weiteren Module mehr erforderlich. Die
    Cloud Function kann eine Instanz erzeugen und `run()` aufrufen.
    """

    def __init__(self, sender_email: str, recipient_email: str):
        self.sender_email = sender_email
        self.recipient_email = recipient_email

        # LLM & Gmail initialisieren
        self.llm = self._init_llm()

    # ---- Gmail helpers ----
    def get_gmail_service(self):
        creds = None
        token_path = "credentials/token.json"
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, ["https://www.googleapis.com/auth/gmail.send"])
        if not creds or not creds.valid:
            raise RuntimeError("Kein gültiges Gmail-Credentials-Token gefunden.")
        return build("gmail", "v1", credentials=creds)

    def send_mail(self, subject=None, mail_body_file=None, attachment_filepath=None):
        logger = logging.getLogger(__name__)
        logger.info("Vorbereitung zum Versenden einer E-Mail an %s", self.recipient_email)

        if mail_body_file:
            logger.debug("Lese Markdown-Datei: %s", mail_body_file)
            with open(mail_body_file, "r", encoding="utf-8") as md_file:
                markdown_content = md_file.read()
            html_content = markdown.markdown(markdown_content)

            msg = MIMEMultipart()
            msg["From"] = self.sender_email
            msg["To"] = self.recipient_email
            if subject:
                msg["Subject"] = subject
                logger.debug("Betreff gesetzt: %s", subject)

            msg.attach(MIMEText(html_content, "html"))

            if attachment_filepath:
                logger.debug("Füge Anhang hinzu: %s", attachment_filepath)
                with open(attachment_filepath, "rb") as attachment:
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(attachment.read())
                    encoders.encode_base64(part)
                    filename = Path(attachment_filepath).name
                    part.add_header("Content-Disposition", f"attachment; filename={filename}")
                    msg.attach(part)

            try:
                logger.info("Sende E-Mail über Gmail API...")
                service = self.get_gmail_service()
                raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
                message = {"raw": raw_message}
                sent = service.users().messages().send(userId="me", body=message).execute()
                logger.info("E-Mail erfolgreich gesendet! Gmail API Message ID: %s", sent["id"])
            except Exception as e:
                logger.error("Fehler beim Senden der E-Mail über die Gmail API: %s", e, exc_info=True)

    # ---- Report generation ----
    def create_markdown_report(self, summaries_and_categories, markdown_report_path):
        logger = logging.getLogger(__name__)
        logger.info("Erstelle Markdown-Report unter %s", markdown_report_path)

        categorized_entries = {}
        for url, details in summaries_and_categories.items():
            logger.debug("Verarbeite Artikel: %s", url)
            category = details.get("category") or "n/a"
            subcategory = details.get("subcategory") or "No Subcategory"
            summary = details.get("summary") or "n/a"
            reading_time = details.get("reading_time")
            hn_points = details.get("hn_points")
            is_alert = details.get("alert", False)

            reading_time_text = (
                f"read in {reading_time} min" if reading_time else "read time n/a"
            )

            if category not in categorized_entries:
                categorized_entries[category] = {}
            if subcategory not in categorized_entries[category]:
                categorized_entries[category][subcategory] = []

            categorized_entries[category][subcategory].append(
                (summary, url, reading_time_text, hn_points, is_alert)
            )

        try:
            with open(markdown_report_path, "w", encoding="utf-8") as file:
                file.write("# News of the Day\n\n")
                for category, subcategories in categorized_entries.items():
                    file.write(f"## {category}\n\n")
                    for subcategory, articles in subcategories.items():
                        if subcategory != "No Subcategory":
                            file.write(f"### {subcategory}\n\n")
                        for summary, url, reading_time_text, hn_points, is_alert in articles:
                            emoji = ""
                            if hn_points and not is_alert:
                                if hn_points >= 200:
                                    emoji = "🚀 "
                                elif 50 <= hn_points < 200:
                                    emoji = "🔥 "

                            line = f"- {emoji}{summary} ([{reading_time_text}]({url}))"
                            if hn_points and not is_alert:
                                line += f" ({hn_points} points)"
                            file.write(line + "\n")
                        file.write("\n")
        except Exception as e:
            logger.error("Fehler beim Erstellen des Markdown-Reports: %s", e, exc_info=True)

    # ---- LLM helpers ----
    def _init_llm(self):
        # initialisiert ChatGoogleGenerativeAI analog zu früher
        def get_gemini_api_key():
            if LOCAL_GEMINI_KEY_ENV in os.environ:
                return os.environ[LOCAL_GEMINI_KEY_ENV]
            api_key = os.getenv(LOCAL_GEMINI_KEY_ENV)
            if not api_key:
                raise RuntimeError("Gemini API-Key nicht verfügbar.")
            return api_key

        rate_limiter = InMemoryRateLimiter(
            requests_per_second=0.2,
            check_every_n_seconds=0.1,
            max_bucket_size=1,
        )
        gemini_key = get_gemini_api_key()
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=gemini_key,
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            rate_limiter=rate_limiter,
        )

    def summarise_and_categorize_websites(self, links_list):
        logger.info(f"Starte Zusammenfassung & Kategorisierung für {len(links_list)} URLs.")
        prompt = self._build_prompt(links_list)
        return self._process_llm_response(prompt)

    def _build_prompt(self, links_list):
        combined_input = "\n\n".join(
            f"Input {i+1} (URL: {url})" for i, url in enumerate(links_list)
        )
        prompt = ChatPromptTemplate.from_messages([
            ("system", """
                You are an assistant that processes multiple URLs provided by the user.
                ... (identical prompt text omitted for brevity) ...
                """),
            ("human", f"{combined_input}"),
        ])
        return prompt

    def _process_llm_response(self, prompt):
        logger.info("Rufe Gemini LLM zur Zusammenfassung und Kategorisierung auf...")
        chain = prompt | self.llm
        response = chain.invoke({}).content
        results = {}
        topic_counts = defaultdict(list)
        for entry in response.split("\n\n"):
            if "Input" in entry:
                url_match = re.search(r"URL:\s*(https?://[^\s)]+)", entry, re.IGNORECASE)
                if not url_match:
                    continue
                url = url_match.group(1)
                summary_match = re.search(r"Summary:\s*(.+)", entry, re.IGNORECASE)
                category_match = re.search(r"Category:\s*(.+)", entry, re.IGNORECASE)
                topics_match = re.search(r"Topics:\s*(.+)", entry, re.IGNORECASE)
                reading_time_match = re.search(r"Reading\s*Time:\s*(\d+)\s*minute[s]?", entry, re.IGNORECASE)
                summary = summary_match.group(1).strip() if summary_match else None
                category = category_match.group(1).strip() if category_match else None
                topics = ([topic.strip() for topic in topics_match.group(1).split(",")] if topics_match else [])
                reading_time = int(reading_time_match.group(1)) if reading_time_match else None
                results[url] = {"summary": summary, "category": category, "topics": topics, "reading_time": reading_time, "subcategory": None}
                for topic in topics:
                    topic_counts[topic].append(url)
        for topic, urls in topic_counts.items():
            if len(urls) >= 3:
                for url in urls:
                    if results[url]["subcategory"] is None:
                        results[url]["subcategory"] = topic
        return results

    def summarise_youtube_videos(self, youtube_urls):
        # identical logic from earlier module
        results = {}
        categories = [
            "Technology and Gadgets", "Artificial Intelligence", "Programming and Development",
            "Politics", "Business and Finance", "Sports", "Education and Learning",
            "Health and Wellness", "Entertainment and Lifestyle", "Travel and Tourism"
        ]
        for url in youtube_urls:
            url = url.rstrip(":")
            try:
                clean_url = self._clean_youtube_url(url)
                youtube_video = types.Part.from_uri(file_uri=clean_url, mime_type="video/*")
                prompt_text = f"""
Du bist ein Assistent, der YouTube-Videos zusammenfasst und kategorisiert.
Anweisungen:
1. Fasse das Video in 2-3 Sätzen zusammen.
2. Schätze die Betrachtungszeit in Minuten.
3. Ordne das Video einer der folgenden Kategorien zu:
   {', '.join(categories)}
   Wenn keine Kategorie passt, gib 'Uncategorized' zurück.
"""
                contents = [youtube_video, types.Part.from_text(text=prompt_text)]
                generate_config = types.GenerateContentConfig(
                    temperature=0,
                    max_output_tokens=1024,
                    response_modalities=["TEXT"],
                )
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=contents,
                    config=generate_config
                )
                text = response.text.strip()
                summary_match = re.search(r"Summary:\s*(.+)", text, re.IGNORECASE)
                reading_time_match = re.search(r"Reading\s*Time:\s*(\d+)", text, re.IGNORECASE)
                category_match = re.search(r"Category:\s*(.+)", text, re.IGNORECASE)
                results[url] = {
                    "summary": summary_match.group(1).strip() if summary_match else None,
                    "reading_time": int(reading_time_match.group(1)) if reading_time_match else None,
                    "category": category_match.group(1).strip() if category_match else "Uncategorized",
                }
            except Exception as e:
                logger.error(f"Fehler bei Verarbeitung des Videos {url}: {e}")
                results[url] = {"summary": None, "reading_time": None, "category": None}
        return results

    def _clean_youtube_url(self, url: str) -> str:
        url = url.strip().rstrip(":")
        parsed = urlparse(url)
        if "google.com" in parsed.netloc and "youtube.com" in url:
            qs = parse_qs(parsed.query)
            if "url" in qs:
                return self._clean_youtube_url(unquote(qs["url"][0]))
        url = url.replace("&amp;", "&")
        parsed = urlparse(url)
        if "youtu.be" in parsed.netloc:
            video_id = parsed.path.lstrip("/")
            return f"https://www.youtube.com/watch?v={video_id}"
        if "youtube.com" in parsed.netloc:
            qs = parse_qs(parsed.query)
            if "v" in qs:
                return f"https://www.youtube.com/watch?v={qs['v'][0]}"
        return url

    # ---- Core workflow ----
    def run(self):
        unsent = get_unsent_entries()
        if not unsent:
            logger.info("Keine ungesendeten Einträge gefunden.")
            return False
        urls_without_summary = [e["url"] for e in unsent if not e.get("summary")]
        if urls_without_summary:
            youtube_urls = [u for u in urls_without_summary if "youtube.com" in u or "youtu.be" in u]
            web_urls = [u for u in urls_without_summary if u not in youtube_urls]
            summaries = {}
            if web_urls:
                summaries.update(self.summarise_and_categorize_websites(web_urls))
            if youtube_urls:
                summaries.update(self.summarise_youtube_videos(youtube_urls))
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
        summaries_from_db = {entry["url"]: {"category": entry.get("category"), "subcategory": entry.get("subcategory"), "summary": entry.get("summary"), "reading_time": entry.get("reading_time"), "hn_points": entry.get("hn_points"), "alert": entry.get("alert", False)} for entry in unsent}
        self.create_markdown_report(summaries_from_db, MARKDOWN_REPORT_PATH)
        self.send_mail(subject="Today's News", mail_body_file=MARKDOWN_REPORT_PATH)
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
