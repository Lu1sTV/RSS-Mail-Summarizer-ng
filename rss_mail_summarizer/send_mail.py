import base64
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
import markdown
from database import get_unsent_entries, mark_as_sent

# Gmail API Service aus alerts_connector importieren
from alerts_connector import get_gmail_service

def send_mail(sender_email, recipient_email, subject=None, mail_body_file=None, attachment_filepath=None):
    if mail_body_file:
        with open(mail_body_file, "r", encoding="utf-8") as md_file:
            markdown_content = md_file.read()
        html_content = markdown.markdown(markdown_content)

        msg = MIMEMultipart()
        msg["From"] = sender_email
        msg["To"] = recipient_email
        if subject:
            msg["Subject"] = subject
        msg.attach(MIMEText(html_content, "html"))

        if attachment_filepath:
            with open(attachment_filepath, "rb") as attachment:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(attachment.read())
                encoders.encode_base64(part)
                filename = Path(attachment_filepath).name
                part.add_header("Content-Disposition", f"attachment; filename={filename}")
                msg.attach(part)

        # ---- Gmail API statt SMTP ----
        try:
            service = get_gmail_service()
            raw_message = base64.urlsafe_b64encode(msg.as_bytes()).decode("utf-8")
            message = {"raw": raw_message}
            sent = service.users().messages().send(userId="me", body=message).execute()
            print(f"Email sent successfully! Gmail API Message ID: {sent['id']}")
            # DB-Einträge als gesendet markieren
            # mark_as_sent(get_unsent_entries())
        except Exception as e:
            print(f"Gmail API error: {e}")

def create_markdown_report(summaries_and_categories, markdown_report_path):
    """ Erstellt eine Markdown-Datei mit allen neuen Artikeln, geordnet nach Kategorien und Subkategorien.
    Alerts haben keine Popularity-Angabe. """
    categorized_entries = {}
    for url, details in summaries_and_categories.items():
        category = details.get("category") or "n/a"
        subcategory = details.get("subcategory") or "No Subcategory"
        summary = details.get("summary") or "n/a"
        reading_time = details.get("reading_time")
        hn_points = details.get("hn_points")
        is_alert = details.get("alert", False)

        # Text für "read in X min" (nur wenn Zahl vorhanden)
        reading_time_text = f"read in {reading_time} min" if reading_time else "read time n/a"

        # Popularity nur, wenn nicht Alert und hn_points vorhanden
        popularity_text = f"(Popularity: {hn_points} points)" if hn_points and not is_alert else None

        if category not in categorized_entries:
            categorized_entries[category] = {}
        if subcategory not in categorized_entries[category]:
            categorized_entries[category][subcategory] = []
        categorized_entries[category][subcategory].append(
            (summary, url, reading_time_text, popularity_text)
        )

    with open(markdown_report_path, "w", encoding="utf-8") as file:
        file.write("# News of the Day\n\n")
        for category, subcategories in categorized_entries.items():
            file.write(f"## {category}\n\n")
            for subcategory, articles in subcategories.items():
                if subcategory != "No Subcategory":
                    file.write(f"### {subcategory}\n\n")
                for summary, url, reading_time_text, popularity_text in articles:
                    line = f"- {summary} ([{reading_time_text}]({url}))"
                    if popularity_text:  # nur hinzufügen, wenn nicht None
                        line += f" {popularity_text}"
                    file.write(line + "\n")
                file.write("\n")