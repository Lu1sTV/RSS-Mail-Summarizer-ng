import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from collections import defaultdict
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





def group_entries_by_category(entries):
    grouped_entries = defaultdict(lambda: defaultdict(list))  # Group by category -> subcategory -> list of articles

    # Durch alle Einträge iterieren und in das Dictionary einfügen
    for entry in entries:
        url, category, subcategory, summary = entry
        grouped_entries[category][subcategory].append((url, summary))

    return grouped_entries


def create_markdown_file(grouped_entries, filename="mail_body.md"):
    with open(filename, "w") as file:
        file.write("# Today's News\n\n")

        # Für jede Kategorie
        for category, subcategories in grouped_entries.items():
            file.write(f"## Category: {category}\n")

            # Für jede Subkategorie in der Kategorie
            for subcategory, articles in subcategories.items():
                file.write(f"### Subcategory: {subcategory}\n")

                # Für jeden Artikel in der Subkategorie
                for url, summary in articles:
                    file.write(f"- **URL**: {url}\n")
                    file.write(f"  **Summary**: {summary}\n")
                file.write("\n")

            file.write("\n---\n\n")


def create_mail_body(file_name="mail_body.md"):
    entries = get_unsent_entries()  # Abrufen der nicht versendeten Einträge
    if entries:
        grouped_entries = group_entries_by_category(entries)  # Gruppieren der Einträge
        create_markdown_file(grouped_entries, file_name)  # Erstellen der Markdown-Datei
        print("Markdown file created successfully!")
    else:
        print("No unsent entries found.")


