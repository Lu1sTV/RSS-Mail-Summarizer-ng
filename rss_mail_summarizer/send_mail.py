"""
Dieses Modul kümmert sich um das Erstellen und Versenden von E-Mails über die Gmail API.
Es wandelt die übergebenen Markdown-Inhalte in HTML um, erstellt einen Report im Markdown-Format.
Außerdem werden verschickte Artikel in der Datenbank als gesendet markiert.
Der Aufruf der Funktion send_mail() findet in der main.py statt.
"""

# package imports
import base64
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import markdown
import os

# Imports eigener Funktionen
from alerts_connector import get_gmail_service
from database import get_unsent_entries, mark_as_sent
from utils.logger import logger


# Sendet eine E-Mail über die Gmail API, optional mit Markdown-Inhalt und Anhang
def send_mail(
    sender_email,
    recipient_email,
    subject=None,
    mail_body_file=None,
    attachment_filepath=None,
):
    logger = logging.getLogger(__name__)
    logger.info("Vorbereitung zum Versenden einer E-Mail an %s", recipient_email)

    # Wenn eine Mail-Body-Datei angegeben ist, wird deren Inhalt als HTML formatiert und in die E-Mail eingefügt
    if mail_body_file:
        logger.debug("Lese Markdown-Datei: %s", mail_body_file)
        with open(mail_body_file, "r", encoding="utf-8") as md_file:
            markdown_content = md_file.read()
        html_content = markdown.markdown(markdown_content)

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient_email
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
                part.add_header(
                    "Content-Disposition", f"attachment; filename={filename}"
                )
                msg.attach(part)

        # E-Mail über die Gmail API senden
        try:
            logger.info("Sende E-Mail über Gmail API...")
            service = get_gmail_service()
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            message = {"raw": raw_message}
            sent = service.users().messages().send(userId="me", body=message).execute()
            logger.info("E-Mail erfolgreich gesendet! Gmail API Message ID: %s", sent["id"])
        except Exception as e:
            logger.error("Fehler beim Senden der E-Mail über die Gmail API: %s", e, exc_info=True)


# Erstellt einen Markdown-Report aus den Artikeldaten, gruppiert nach Kategorie und Subkategorie
def create_markdown_report(summaries_and_categories, markdown_report_path):
    logger = logging.getLogger(__name__)
    logger.info("Erstelle Markdown-Report unter %s", markdown_report_path)

    categorized_entries = {}
    # Artikel nach Kategorie und Subkategorie gruppieren
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
                        # Emoji basierend auf HN-Punkten bestimmen
                        emoji = ""
                        if hn_points and not is_alert:
                            if hn_points >= 200:
                                emoji = "🚀 "
                            elif 50 <= hn_points < 200:
                                emoji = "🔥 "

                        line = f"- {emoji}{summary} ([{reading_time_text}]({url}))"

                        # Punkte anhängen, falls vorhanden
                        if hn_points and not is_alert:
                            line += f" ({hn_points} points)"

                        file.write(line + "\n")
                    file.write("\n")
    except Exception as e:
        logger.error("Fehler beim Erstellen des Markdown-Reports: %s", e, exc_info=True)

