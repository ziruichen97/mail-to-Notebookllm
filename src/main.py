"""Entry point — single-run email polling for GitHub Actions."""

from __future__ import annotations

import sys
from datetime import datetime

from src.auth_guard import check_subject_key, is_authorized
from src.config import AppConfig, load_config
from src.email_client import fetch_unseen_emails, mark_as_seen, send_reply
from src.link_processor import extract_category, extract_links
from src.link_validator import validate_links
from src.logger import setup_logger
from src.models import ProcessingResult, SubmitStatus, ValidationStatus
from src.notebooklm_writer import create_writer
from src.notification import build_reply_body


def _get_notebook_name(category: str | None, config: AppConfig) -> str:
  if category:
    return category
  if config.notebooklm.default_category == "monthly":
    return datetime.now().strftime("%Y-%m 视频收藏")
  return config.notebooklm.default_category


def _extract_sender_address(sender: str) -> str:
  """Extract bare email address from 'Display Name <addr>' format."""
  if "<" in sender and ">" in sender:
    return sender.split("<")[1].split(">")[0].strip()
  return sender.strip()


def process_email(uid, email_msg, config, writer, logger) -> ProcessingResult:
  """Process a single email through the full pipeline."""
  result = ProcessingResult(email=email_msg)

  # Step 1: Authorization
  if not is_authorized(email_msg.sender, config.auth):
    result.authorized = False
    logger.info("Email rejected — unauthorized sender")
    return result

  if not check_subject_key(email_msg.subject, config.auth):
    result.authorized = False
    logger.info("Email rejected — subject key mismatch")
    return result

  # Step 2: Extract links
  links = extract_links(
    email_msg.body_text,
    email_msg.body_html,
    config.link_processing.supported_platforms,
    allow_generic=config.link_processing.allow_generic_urls,
  )
  email_msg.links = links
  result.links_found = len(links)

  if not links:
    logger.info("No video links found in email")
    return result

  # Step 3: Validate links
  valid_links, invalid_links = validate_links(
    links,
    timeout=config.link_processing.validation_timeout,
    max_retries=config.link_processing.max_retries,
  )
  result.links_valid = len(valid_links)

  if not valid_links:
    logger.info("No valid links after validation")
    result.links_failed = len(invalid_links)
    return result

  # Step 4: Determine category / notebook
  category = extract_category(email_msg.subject)
  email_msg.category = category
  notebook_name = _get_notebook_name(category, config)
  result.notebook_name = notebook_name

  # Step 5: Submit to NotebookLM
  try:
    notebook_id = writer.ensure_notebook(notebook_name)
    result.notebook_id = notebook_id
    writer.add_sources(notebook_id, valid_links)
  except Exception:
    logger.exception("NotebookLM write failed")
    for link in valid_links:
      link.submit_status = SubmitStatus.FAILED
      link.error_message = "NotebookLM write failed"
    result.error_message = "NotebookLM integration error"

  result.links_submitted = sum(
    1 for l in valid_links if l.submit_status == SubmitStatus.SUBMITTED
  )
  result.links_failed = (
    len(invalid_links) +
    sum(1 for l in valid_links if l.submit_status == SubmitStatus.FAILED)
  )

  return result


def run(config_path: str | None = None) -> int:
  logger = setup_logger()
  logger.info("--- Mail-to-NotebookLM polling start ---")

  try:
    config = load_config(config_path)
  except Exception:
    logger.exception("Failed to load configuration")
    return 1

  if not config.email.username or not config.email.password:
    logger.error("EMAIL_USERNAME and EMAIL_PASSWORD must be set")
    return 1

  # Fetch unseen emails
  try:
    emails = fetch_unseen_emails(config.email)
  except Exception:
    logger.exception("Failed to fetch emails")
    return 1

  if not emails:
    logger.info("No new emails — exiting")
    return 0

  # Initialize NotebookLM writer
  try:
    writer = create_writer(config.notebooklm)
  except Exception:
    logger.exception("Failed to initialize NotebookLM writer")
    return 1

  processed_uids: list[int] = []
  total_submitted = 0
  total_failed = 0

  for uid, email_msg in emails:
    logger.info("Processing email (subject has %d chars)", len(email_msg.subject))

    result = process_email(uid, email_msg, config, writer, logger)

    if not result.authorized:
      continue

    total_submitted += result.links_submitted
    total_failed += result.links_failed

    # Send reply if configured
    if config.notification.send_reply and result.links_found > 0:
      try:
        sender_addr = _extract_sender_address(email_msg.sender)
        reply_body = build_reply_body(result)
        send_reply(config.email, sender_addr, email_msg.subject, reply_body)
      except Exception:
        logger.exception("Failed to send reply")

    processed_uids.append(uid)

  # Mark processed emails as seen
  if processed_uids:
    mark_as_seen(config.email, processed_uids)

  logger.info(
    "--- Polling complete: %d email(s) processed, %d link(s) submitted, %d failed ---",
    len(processed_uids), total_submitted, total_failed,
  )
  return 0


if __name__ == "__main__":
  config_file = sys.argv[1] if len(sys.argv) > 1 else None
  sys.exit(run(config_file))
