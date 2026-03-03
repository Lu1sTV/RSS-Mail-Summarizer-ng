import os
import json
import base64
import logging
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.rate_limiters import InMemoryRateLimiter
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

# --------------------- Utilities ---------------------------------------
LOCAL_GEMINI_KEY_ENV = "GEMINI_API_KEY"
SECRET_ENV = "RSS_VERTEX_AI_KEY"


def _sanitize_api_key(raw_value, env_name):
    if not raw_value:
        return None
    value = str(raw_value).strip().strip('"').strip("'")
    if not value:
        return None
    if value.startswith("{"):
        try:
            payload = json.loads(value)
            for field in ("api_key", "gemini_api_key", "GEMINI_API_KEY", "key"):
                extracted = payload.get(field)
                if isinstance(extracted, str) and extracted.strip():
                    value = extracted.strip()
                    break
            else:
                logger.warning("Umgebungsvariable %s enthält JSON ohne API-Key-Feld und wird ignoriert.", env_name)
                return None
        except Exception:
            logger.warning("Umgebungsvariable %s enthält ungültiges JSON und wird als Plain-Text versucht.", env_name)
    value = value.replace("\r", "").replace("\n", "")
    if any(char.isspace() for char in value):
        value = "".join(value.split())
    return value or None


def get_gemini_api_key():
    candidates = [LOCAL_GEMINI_KEY_ENV, SECRET_ENV, "GOOGLE_API_KEY"]
    for env_name in candidates:
        sanitized = _sanitize_api_key(os.getenv(env_name), env_name)
        if sanitized:
            logger.info("Gemini API-Key aus %s geladen.", env_name)
            return sanitized
    return None


# --------------------- Gmail helpers ----------------------------------
def get_gmail_service():
    creds = None
    scopes = ["https://www.googleapis.com/auth/gmail.modify"]
    token_json_str = os.environ.get("CREDENTIALS_TOKEN_JSON")
    if token_json_str:
        try:
            creds_info = json.loads(token_json_str)
            creds = Credentials.from_authorized_user_info(creds_info, scopes)
            logger.info("Gmail-Token erfolgreich aus Secret Manager geladen.")
        except Exception as e:
            logger.error(f"Fehler beim Parsen des Tokens aus Umgebungsvariable: {e}")
    if not creds:
        token_path = "credentials/token.json"
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, scopes)
            logger.info(f"Gmail-Token aus lokaler Datei geladen: {token_path}")
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            logger.info("Gmail-Token wurde erfolgreich erneuert (refreshed).")
        else:
            raise RuntimeError("Kein gültiges Gmail-Token gefunden. Stelle sicher, dass CREDENTIALS_TOKEN_JSON im Secret Manager korrekt gesetzt ist.")
    return build("gmail", "v1", credentials=creds)


def gmail_send_mail(sender_email, recipient_email, subject=None, mail_body_file=None, attachment_filepath=None):
    logger.info("Vorbereitung zum Versenden einer E-Mail an %s", recipient_email)
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    if subject:
        msg["Subject"] = subject
        logger.debug("Betreff gesetzt: %s", subject)
    if mail_body_file:
        logger.debug("Lese Markdown-Datei: %s", mail_body_file)
        import markdown
        with open(mail_body_file, "r", encoding="utf-8") as md_file:
            markdown_content = md_file.read()
        html_content = markdown.markdown(markdown_content)
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
        service = get_gmail_service()
        raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
        message = {"raw": raw_message}
        sent = service.users().messages().send(userId="me", body=message).execute()
        logger.info("E-Mail erfolgreich gesendet! Gmail API Message ID: %s", sent["id"])
    except Exception as e:
        logger.error("Fehler beim Senden der E-Mail über die Gmail API: %s", e, exc_info=True)


# --------------------- Report generator --------------------------------
def create_markdown_report(summaries_and_categories, markdown_report_path):
    logger.info("Erstelle Markdown-Report unter %s", markdown_report_path)
    categorized_entries = {}
    for url, details in summaries_and_categories.items():
        logger.debug("Verarbeite Artikel: %s", url)
        category = details.get("category") or "Uncategorized"
        subcategory = details.get("subcategory") or "No Subcategory"
        summary = details.get("summary")
        if not summary or str(summary).strip().lower() in ["n/a", "none", "null"]:
            summary = "(keine Zusammenfassung verfügbar)"
        reading_time = details.get("reading_time")
        hn_points = details.get("hn_points")
        is_alert = details.get("alert", False)
        reading_time_text = (f"read in {reading_time} min" if reading_time else "read time n/a")
        if category not in categorized_entries:
            categorized_entries[category] = {}
        if subcategory not in categorized_entries[category]:
            categorized_entries[category][subcategory] = []
        categorized_entries[category][subcategory].append((summary, url, reading_time_text, hn_points, is_alert))
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


# --------------------- AI Service (lazy init, 1:1 from llm_calls.py) --------
class AIService:
    def __init__(self, gemini_api_key: str):
        self.gemini_api_key = gemini_api_key
        self.genai_client = None
        self.llm = None

    def _init_llm(self):
        rate_limiter = InMemoryRateLimiter(requests_per_second=0.2, check_every_n_seconds=0.1, max_bucket_size=1)
        return ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            google_api_key=self.gemini_api_key,
            temperature=0,
            max_tokens=None,
            timeout=None,
            max_retries=2,
            rate_limiter=rate_limiter,
        )

    def _ensure_ai_clients(self):
        if self.llm is not None and self.genai_client is not None:
            return
        if not self.gemini_api_key:
            raise RuntimeError("Kein gültiger Gemini API-Key gefunden. Bitte setze GEMINI_API_KEY (oder RSS_VERTEX_AI_KEY als Fallback) als Secret ohne Zeilenumbrüche.")
        self.genai_client = genai.Client(api_key=self.gemini_api_key)
        self.llm = self._init_llm()

    def summarise_and_categorize_websites(self, links_list):
        """Fasst URLs zusammen und kategorisiert sie (1:1 von llm_calls.py)."""
        self._ensure_ai_clients()
        logger.info(f"Starte Zusammenfassung & Kategorisierung für {len(links_list)} URLs.")
        prompt = self._build_prompt(links_list)
        return self._process_llm_response(prompt)

    def _build_prompt(self, links_list):
        """Erstellt den Prompt für Gemini (EXAKT wie in llm_calls.py)."""
        logger.debug("Erstelle Prompt für Gemini-Anfrage...")
        combined_input = "\n\n".join(f"Input {i+1} (URL: {url})" for i, url in enumerate(links_list))

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """
                You are an assistant that processes multiple URLs provided by the user.
                For each input, perform the following tasks:

                1. Summarize the content of the Website in about 3 sentences.
                2. Categorize it into one of the following categories:
                   - Technology and Gadgets
                   - Artificial Intelligence
                   - Programming and Development
                   - Politics
                   - Business and Finance
                   - Sports
                   - Education and Learning
                   - Health and Wellness
                   - Entertainment and Lifestyle
                   - Travel and Tourism
                   If a website does not fit into one of these categories, return 'Uncategorized'.
                3. Identify specific topics or entities mentioned in the articles. These should be precise and clearly defined, such as names of technologies, events, organizations, or specific concepts discussed in the text.
                4. Estimate the reading time of the article in minutes based on the length and complexity of the content. Make sure you assess each article individually!
                
                SPECIAL RULE FOR GITHUB URLs:
                - If the URL is a GitHub **repository** page, set Category **exactly** to "GitHub" (override the list above).
                - If content is a **GitHub Blog** Post, treat it like any other website, do not categorize it as "GitHub". Check the content of the page to determine if it is a blog post.
                DO NOT use the "GitHub" category; choose from the normal list above if the post is a blog post. Only repositories should be categorized as "GitHub".
                
                If you are unable to access the contents of the provided website, return "Website content could not be reached!" for that input.

                Format your response as follows:
                Input 1 (URL: <url>):
                Summary: <summary>
                Category: <category> # "GitHub" only for repository URLs as defined above
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                Input 2 (URL: <url>):
                Summary: <summary>
                Category: <category>
                Topics: <topic1>, <topic2>, ...
                Reading Time: <X> minutes

                ...

                Ensure that the topics are specific and relevant to the main content of the article.
                """,
                ),
                ("human", f"{combined_input}"),
            ]
        )

        logger.debug("Prompt erfolgreich erstellt.")
        return prompt

    def _process_llm_response(self, prompt):
        """Verarbeitet LLM-Ausgabe und extrahiert strukturierte Daten (EXAKT wie in llm_calls.py)."""
        logger.info("Rufe Gemini LLM zur Zusammenfassung und Kategorisierung auf...")
        chain = prompt | self.llm
        response = chain.invoke({}).content
        logger.debug(f"LLM raw response:\n{response}")

        results = {}
        topic_counts = defaultdict(list)

        for entry in response.split("\n\n"):
            if "Input" in entry:
                url_match = re.search(r"URL:\s*(https?://[^\s)]+)", entry, re.IGNORECASE)
                if not url_match:
                    logger.warning("URL konnte aus Eintrag nicht extrahiert werden, überspringe Eintrag.")
                    continue

                url = url_match.group(1)
                summary_match = re.search(r"Summary:\s*(.+)", entry, re.IGNORECASE)
                category_match = re.search(r"Category:\s*(.+)", entry, re.IGNORECASE)
                topics_match = re.search(r"Topics:\s*(.+)", entry, re.IGNORECASE)
                reading_time_match = re.search(r"Reading\s*Time:\s*(\d+)\s*minute[s]?", entry, re.IGNORECASE)

                summary = summary_match.group(1).strip() if summary_match else None
                category = category_match.group(1).strip() if category_match else None
                topics = ([topic.strip() for topic in topics_match.group(1).split(",")] if topics_match else [])
                reading_time = (int(reading_time_match.group(1)) if reading_time_match else None)

                results[url] = {
                    "summary": summary,
                    "category": category,
                    "topics": topics,
                    "reading_time": reading_time,
                    "subcategory": None,
                }
                logger.debug(f"Eintrag für URL {url} mit Kategorie '{category}' verarbeitet.")

                for topic in topics:
                    topic_counts[topic].append(url)

        # Subkategorisierung basierend auf Themen
        for topic, urls in topic_counts.items():
            if len(urls) >= 3:
                logger.info(f"Subkategorie '{topic}' für {len(urls)} URLs zugewiesen.")
                for url in urls:
                    if results[url]["subcategory"] is None:
                        results[url]["subcategory"] = topic

        return results

    def summarise_alerts(self, alerts_dict):
        """Erstellt Zusammenfassungen für Google Alerts (EXAKT wie in llm_calls.py)."""
        logger.info(f"Starte Zusammenfassung für {len(alerts_dict)} Google Alerts.")
        self._ensure_ai_clients()
        all_results = {}
        for label, urls in alerts_dict.items():
            logger.debug(f"Verarbeite Alert '{label}' mit {len(urls)} URLs.")
            combined_input = "\n".join(f"{url}" for url in urls)
            prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        f"""
            You are an assistant that summarizes multiple URLs for the alert '{label}'.
            For each URL, provide:
            1. Summary (2-3 sentences)
            2. Estimated reading time in minutes

            If you cannot access the website, return:
            "Website content could not be reached!"

            Format your response as follows:
            <URL>:
            Summary: <summary>
            Reading Time: <X> minutes
            """,
                    ),
                    ("human", combined_input),
                ]
            )
            result = self._process_alert_response(prompt, urls)
            all_results.update(result)
        return all_results

    def _process_alert_response(self, prompt, urls):
        """Verarbeitet Gemini Antwort für Google Alerts (EXAKT wie in llm_calls.py)."""
        logger.info("Rufe Gemini LLM für Google Alerts Zusammenfassung auf...")
        chain = prompt | self.llm
        response = chain.invoke({}).content
        logger.debug(f"LLM alert raw response:\n{response}")

        results = {}
        for entry in response.split("\n\n"):
            url_match = re.search(r"(https?://\S+)", entry)
            summary_match = re.search(r"Summary:\s*(.+)", entry, re.IGNORECASE)
            reading_time_match = re.search(r"Reading\s*Time:\s*(\d+)\s*minute[s]?", entry, re.IGNORECASE)

            if url_match:
                url = url_match.group(1)
                results[url] = {
                    "summary": summary_match.group(1).strip() if summary_match else None,
                    "reading_time": (int(reading_time_match.group(1)) if reading_time_match else None),
                }
                logger.debug(f"Eintrag für Alert-URL {url} verarbeitet.")
            else:
                logger.warning("Konnte URL aus Gemini Alert-Antwort nicht extrahieren.")

        return results

    def summarise_youtube_videos(self, youtube_urls):
        """Fasst YouTube-Videos zusammen und kategorisiert sie."""
        self._ensure_ai_clients()
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
                generate_config = types.GenerateContentConfig(temperature=0, max_output_tokens=1024, response_modalities=["TEXT"])
                response = self.genai_client.models.generate_content(model="gemini-2.5-flash", contents=contents, config=generate_config)
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

    def summarise_youtube_alerts(self, youtube_urls):
        """Fasst YouTube-Videos aus Google Alerts zusammen."""
        self._ensure_ai_clients()
        results = {}
        for url in youtube_urls:
            url = url.rstrip(":")
            try:
                clean_url = self._clean_youtube_url(url)
                youtube_video = types.Part.from_uri(file_uri=clean_url, mime_type="video/*")
                prompt_text = """
Du bist ein Assistent, der YouTube-Videos aus Google Alerts zusammenfasst.
Anweisungen:
1. Fasse das Video in 2-3 Sätzen zusammen.
2. Schätze die Betrachtungszeit in Minuten.

Format:
Summary: <Zusammenfassung>
Reading Time: <geschätzte Minuten>
"""
                contents = [youtube_video, types.Part.from_text(text=prompt_text)]
                generate_config = types.GenerateContentConfig(temperature=0, max_output_tokens=1024, response_modalities=["TEXT"])
                response = self.genai_client.models.generate_content(model="gemini-2.5-flash", contents=contents, config=generate_config)
                text = response.text.strip()
                summary_match = re.search(r"Summary:\s*(.+)", text, re.IGNORECASE)
                reading_time_match = re.search(r"Reading\s*Time:\s*(\d+)", text, re.IGNORECASE)
                results[url] = {"summary": summary_match.group(1).strip() if summary_match else None, "reading_time": int(reading_time_match.group(1)) if reading_time_match else None}
                logger.info(f"Alert erfolgreich verarbeitet: {url}")
            except Exception as e:
                logger.error(f"Fehler bei Verarbeitung des Alerts {url}: {e}")
                results[url] = {"summary": None, "reading_time": None}
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
