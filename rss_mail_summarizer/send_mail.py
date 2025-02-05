import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path


# currently no attachments are supported (should maybe be added later)
def send_mail(sender_email, sender_password, recipient_email, subject=None, text_body="", attachment_filepath=None):

    # create email
    msg = MIMEMultipart()
    msg["From"] = sender_email
    msg["To"] = recipient_email
    if subject:
        msg["Subject"] = subject
    msg.attach(MIMEText(text_body, "plain"))

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
    except smtplib.SMTPException as e:
        print(f"SMTP error: {e}")
    except Exception as e:
        print(f"Other error: {e}")





