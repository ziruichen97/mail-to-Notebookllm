"""Sender authorization — whitelist matching with wildcard support."""

from __future__ import annotations

import fnmatch
import logging

from src.config import AuthConfig

logger = logging.getLogger("mail2nlm")


def is_authorized(sender: str, config: AuthConfig) -> bool:
  sender_lower = sender.lower().strip()

  # Strip display name: "John <john@example.com>" → "john@example.com"
  if "<" in sender_lower and ">" in sender_lower:
    sender_lower = sender_lower.split("<")[1].split(">")[0].strip()

  if not config.allowed_senders:
    logger.warning("No allowed senders configured — rejecting all")
    return False

  for pattern in config.allowed_senders:
    if fnmatch.fnmatch(sender_lower, pattern.lower()):
      logger.info("Sender authorized (matched pattern)")
      return True

  logger.info("Sender not in whitelist — rejected")
  return False


def check_subject_key(subject: str, config: AuthConfig) -> bool:
  if not config.require_subject_key:
    return True

  if not config.subject_key:
    logger.warning("Subject key required but not configured")
    return False

  if config.subject_key in subject:
    logger.info("Subject key verified")
    return True

  logger.info("Subject key missing or incorrect — rejected")
  return False
