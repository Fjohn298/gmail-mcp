"""Envío de correos HTML a través de cualquier MailSender."""
import base64
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from gmailmcp.gmail.ports import MailSender


class EmailNotifier:
    def __init__(self, sender: MailSender):
        self._sender = sender

    def send_html(self, to: str, subject: str, html: str) -> None:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = 'me'
        msg['To'] = to
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        self._sender.send_raw(base64.urlsafe_b64encode(msg.as_bytes()).decode())
