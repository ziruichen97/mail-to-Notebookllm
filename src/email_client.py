"""IMAP email fetching (polling mode) and SMTP reply sending."""

from __future__ import annotations

import email
import email.utils
import logging
import smtplib
import ssl
from datetime import datetime
from email.header import decode_header
from email.mime.text import MIMEText

from imapclient import IMAPClient

from src.config import EmailConfig
from src.models import EmailMessage

logger = logging.getLogger("mail2nlm")

# Avoid hanging on bad networks (CI, strict firewalls)
_SMTP_TIMEOUT_SEC = 30

# Shown in IMAP ID (RFC 2971); Netease requires this before SELECT — see Netease IMAP FAQ.
_IMAP_CLIENT_NAME = "MailToNotebookLM"
_IMAP_CLIENT_VERSION = "1.0.0"
_IMAP_VENDOR = "mail-to-notebooklm"


def _default_imap_client_id(username: str) -> dict[str, str]:
  """Default ID fields; Netease examples use name, version, vendor, support-email."""
  support = username.strip() if "@" in username else "noreply@localhost"
  return {
    "name": _IMAP_CLIENT_NAME,
    "version": _IMAP_CLIENT_VERSION,
    "vendor": _IMAP_VENDOR,
    "support-email": support,
  }


def _send_imap_client_id(client: IMAPClient, config: EmailConfig) -> None:
  """Send IMAP ID after login, before SELECT. Required by Netease (163/126/188) IMAP."""
  if not config.imap.send_client_id:
    return
  params = config.imap.client_id or _default_imap_client_id(config.username)
  client.id_(params)
  logger.debug("IMAP ID (RFC 2971) sent")


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
    _send_imap_client_id(client, config)
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
    _send_imap_client_id(client, config)
    client.select_folder(config.folder, readonly=False)
    client.add_flags(uids, [b"\\Seen"])
    client.logout()
    logger.info("Marked %d email(s) as seen", len(uids))
  except Exception:
    logger.exception("Failed to mark emails as seen")


def send_reply(config: EmailConfig, to_addr: str, subject: str, body: str) -> None:
  """Send a plain-text reply email via SMTP.

  ``smtp.use_tls`` True: plain connect + STARTTLS (typical Gmail/Outlook port 587).
  ``smtp.use_tls`` False: implicit TLS via SMTP_SSL (typical Netease port 465).
  """
  try:
    msg = MIMEText(body, "plain", "utf-8")
    msg["From"] = config.username
    msg["To"] = to_addr
    msg["Subject"] = f"Re: {subject}"

    tls_ctx = ssl.create_default_context()

    if config.smtp.use_tls:
      server = smtplib.SMTP(
        config.smtp.host, config.smtp.port, timeout=_SMTP_TIMEOUT_SEC,
      )
      try:
        server.starttls(context=tls_ctx)
      except Exception:
        server.close()
        raise
    else:
      server = smtplib.SMTP_SSL(
        config.smtp.host,
        config.smtp.port,
        context=tls_ctx,
        timeout=_SMTP_TIMEOUT_SEC,
      )

    try:
      server.login(config.username, config.password)
      server.send_message(msg)
    finally:
      try:
        server.quit()
      except Exception:
        server.close()

    logger.info("Reply email sent")
  except Exception:
    logger.exception("Failed to send reply email")
