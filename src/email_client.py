"""IMAP email fetching (polling mode) and SMTP reply sending."""

from __future__ import annotations

import email
import email.utils
import logging
import smtplib
from datetime import datetime
from email.header import decode_header
from email.mime.text import MIMEText

from imapclient import IMAPClient

from src.config import EmailConfig
from src.models import EmailMessage

logger = logging.getLogger("mail2nlm")


def _decode_header_value(raw: str | bytes | None) -> str:
  if raw is None:
    return ""
  if isinstance(raw, bytes):
    raw = raw.decode("utf-8", errors="replace")
  decoded_parts = decode_header(raw)
  parts: list[str] = []
  for data, charset in decoded_parts:
    if isinstance(data, bytes):
      parts.append(data.decode(charset or "utf-8", errors="replace"))
    else:
      parts.append(str(data))
  return "".join(parts)


def _extract_body(msg: email.message.Message) -> tuple[str, str | None]:
  """Extract plain-text and HTML body from an email message."""
  body_text = ""
  body_html: str | None = None

  if msg.is_multipart():
    for part in msg.walk():
      content_type = part.get_content_type()
      if content_type == "text/plain" and not body_text:
        payload = part.get_payload(decode=True)
        if payload:
          charset = part.get_content_charset() or "utf-8"
          body_text = payload.decode(charset, errors="replace")
      elif content_type == "text/html" and body_html is None:
        payload = part.get_payload(decode=True)
        if payload:
          charset = part.get_content_charset() or "utf-8"
          body_html = payload.decode(charset, errors="replace")
  else:
    payload = msg.get_payload(decode=True)
    if payload:
      charset = msg.get_content_charset() or "utf-8"
      content = payload.decode(charset, errors="replace")
      if msg.get_content_type() == "text/html":
        body_html = content
      else:
        body_text = content

  return body_text, body_html


def fetch_unseen_emails(config: EmailConfig) -> list[tuple[int, EmailMessage]]:
  """Connect to IMAP and fetch all unseen emails. Returns (uid, message) pairs."""
  results: list[tuple[int, EmailMessage]] = []

  try:
    client = IMAPClient(config.imap.host, port=config.imap.port, ssl=config.imap.use_ssl)
    client.login(config.username, config.password)
    client.select_folder(config.folder, readonly=False)

    uids = client.search(["UNSEEN"])
    if not uids:
      logger.info("No new emails found")
      client.logout()
      return results

    logger.info("Found %d new email(s)", len(uids))

    raw_messages = client.fetch(uids, ["RFC822", "INTERNALDATE"])

    for uid in uids:
      try:
        raw = raw_messages[uid]
        msg = email.message_from_bytes(raw[b"RFC822"])
        internal_date = raw.get(b"INTERNALDATE", datetime.now())

        sender = _decode_header_value(msg.get("From", ""))
        subject = _decode_header_value(msg.get("Subject", ""))
        message_id = msg.get("Message-ID", f"uid-{uid}")
        body_text, body_html = _extract_body(msg)

        email_msg = EmailMessage(
          message_id=message_id,
          sender=sender,
          subject=subject,
          body_text=body_text,
          body_html=body_html,
          received_at=internal_date if isinstance(internal_date, datetime) else datetime.now(),
        )
        results.append((uid, email_msg))
      except Exception:
        logger.exception("Failed to parse email uid=%s", uid)

    client.logout()
  except Exception:
    logger.exception("IMAP connection failed")

  return results


def mark_as_seen(config: EmailConfig, uids: list[int]) -> None:
  """Mark emails as SEEN so they won't be fetched again."""
  if not uids:
    return
  try:
    client = IMAPClient(config.imap.host, port=config.imap.port, ssl=config.imap.use_ssl)
    client.login(config.username, config.password)
    client.select_folder(config.folder, readonly=False)
    client.add_flags(uids, [b"\\Seen"])
    client.logout()
    logger.info("Marked %d email(s) as seen", len(uids))
  except Exception:
    logger.exception("Failed to mark emails as seen")


def send_reply(config: EmailConfig, to_addr: str, subject: str, body: str) -> None:
  """Send a plain-text reply email via SMTP."""
  try:
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = config.username
    msg["To"] = to_addr
    msg["Subject"] = f"Re: {subject}"

    if config.smtp.use_tls:
      server = smtplib.SMTP(config.smtp.host, config.smtp.port)
      server.starttls()
    else:
      server = smtplib.SMTP_SSL(config.smtp.host, config.smtp.port)

    server.login(config.username, config.password)
    server.send_message(msg)
    server.quit()
    logger.info("Reply email sent")
  except Exception:
    logger.exception("Failed to send reply email")
