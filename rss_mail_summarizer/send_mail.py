import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from database import get_unsent_entries, mark_as_sent
import markdown


# currently no attachments are supported (should maybe be added later)
def send_mail(sender_email, sender_password, recipient_email, subject=None, mail_body_file=None, attachment_filepath=None):

    if mail_body_file:
        with open(mail_body_file, "r") as md_file:
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

    # Connect to the SMTP server and send email
    try:
        s = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)
        s.login(sender_email, sender_password)
        s.sendmail(sender_email, recipient_email, msg.as_string())
        s.quit()
        print("Email sent successfully!")

        # versendete Artikel werden in der Datenbank als solche markiert
        mark_as_sent(get_unsent_entries())

    except smtplib.SMTPException as e:
        print(f"SMTP error: {e}")
    except Exception as e:
        print(f"Other error: {e}")




def create_markdown_report(summaries_and_categories, markdown_report_path):
    """
    Erstellt eine Markdown-Datei mit allen neuen Artikeln, geordnet nach Kategorien und Subkategorien.

    Input:
    - summaries_and_categories (dict): Ein Dictionary mit URLs als Schlüssel und Werten, die ein Dictionary mit
      'summary', 'category' und 'subcategory' sind.

    Output:
    - Erstellt eine Markdown-Datei mit dem Namen "news_report.md".
    """
    # Dictionary zur Organisation der Artikel nach Kategorien und Subkategorien
    categorized_entries = {}

    for url, details in summaries_and_categories.items():
        category = details["category"]
        subcategory = details["subcategory"]
        summary = details["summary"]
        reading_time = details["reading_time"]

        if category not in categorized_entries:
            categorized_entries[category] = {}

        if subcategory:
            if subcategory not in categorized_entries[category]:
                categorized_entries[category][subcategory] = []
            categorized_entries[category][subcategory].append((summary, url))
        else:
            if "No Subcategory" not in categorized_entries[category]:
                categorized_entries[category]["No Subcategory"] = []
            categorized_entries[category][subcategory].append((summary, url, reading_time))

    with open(markdown_report_path, "w") as file:
        # Überschrift
        file.write("# News of the Day\n\n")

        for category, subcategories in categorized_entries.items():
            # Kategorie-Überschrift
            file.write(f"## {category}\n\n")

            for subcategory, articles in subcategories.items():
                if subcategory == "No Subcategory":
                    # Artikel ohne Subkategorie direkt unter der Kategorie auflisten
                    for summary, url, reading_time in articles:
                        file.write(f"- {summary} [(read in {reading_time} min)]({url})\n")
                else:
                    # Subkategorie-Überschrift
                    file.write(f"### {subcategory}\n\n")
                    for summary, url in articles:
                        file.write(f"- {summary} [(read in {reading_time} min)]({url})\n")

            file.write("\n")




