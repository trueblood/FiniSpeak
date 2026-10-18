"""SMTP delivery for verification and password recovery messages."""

import os
import smtplib
import ssl
from email.message import EmailMessage


def send_account_link(recipient, subject, path, token):
    host, sender = os.getenv("FINISPEAK_SMTP_HOST", "").strip(), os.getenv("FINISPEAK_EMAIL_FROM", "").strip()
    base_url = os.getenv("FINISPEAK_PUBLIC_URL", "").strip().rstrip("/")
    if not host or not sender or not base_url:
        raise RuntimeError("Email delivery is not configured.")
    message = EmailMessage(); message["From"], message["To"], message["Subject"] = sender, recipient, subject
    message.set_content(f"Open this FiniSpeak link to continue:\n\n{base_url}{path}?token={token}\n\nThis link expires automatically and can be used once.")
    port, username, password = int(os.getenv("FINISPEAK_SMTP_PORT", "465")), os.getenv("FINISPEAK_SMTP_USERNAME", "").strip(), os.getenv("FINISPEAK_SMTP_PASSWORD", "")
    security = os.getenv("FINISPEAK_SMTP_SECURITY", "ssl").strip().lower()
    if security == "ssl":
        client = smtplib.SMTP_SSL(host, port, context=ssl.create_default_context(), timeout=20)
    elif security == "starttls":
        client = smtplib.SMTP(host, port, timeout=20)
        client.ehlo(); client.starttls(context=ssl.create_default_context()); client.ehlo()
    else:
        raise RuntimeError("FINISPEAK_SMTP_SECURITY must be ssl or starttls.")
    with client:
        if username: client.login(username, password)
        client.send_message(message)
