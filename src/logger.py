"""Sanitized logging — strips emails, URLs, and credentials from log output."""

from __future__ import annotations

import logging
import re
from typing import Any

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")
_PLATFORM_LABEL = {
  "youtube.com": "YouTube",
  "youtu.be": "YouTube",
  "bilibili.com": "Bilibili",
  "b23.tv": "Bilibili",
  "vimeo.com": "Vimeo",
  "ted.com": "TED",
}


def _mask_email(match: re.Match) -> str:
  email = match.group()
  local, domain = email.split("@", 1)
  if len(local) <= 2:
    masked = local[0] + "***"
  else:
    masked = local[0] + "***" + local[-1]
  return f"{masked}@{domain}"


def _mask_url(match: re.Match) -> str:
  url = match.group()
  for domain_fragment, label in _PLATFORM_LABEL.items():
    if domain_fragment in url:
      return f"[{label}:***]"
  try:
    from urllib.parse import urlparse
    parsed = urlparse(url)
    return f"[{parsed.netloc}:***]"
  except Exception:
    return "[URL:***]"


def sanitize(text: str) -> str:
  text = _EMAIL_RE.sub(_mask_email, text)
  text = _URL_RE.sub(_mask_url, text)
  return text


class SanitizingFormatter(logging.Formatter):
  """Formatter that masks sensitive data before writing to output."""

  def format(self, record: logging.LogRecord) -> str:
    record.msg = sanitize(str(record.msg))
    if record.args:
      record.args = tuple(
        sanitize(str(a)) if isinstance(a, str) else a
        for a in (record.args if isinstance(record.args, tuple) else (record.args,))
      )
    return super().format(record)


def setup_logger(name: str = "mail2nlm", level: int = logging.INFO) -> logging.Logger:
  logger = logging.getLogger(name)
  if logger.handlers:
    return logger
  logger.setLevel(level)

  handler = logging.StreamHandler()
  handler.setFormatter(
    SanitizingFormatter("[%(asctime)s] %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S")
  )
  logger.addHandler(handler)
  return logger


def log_raw(logger: logging.Logger, level: int, msg: str, *args: Any) -> None:
  """Bypass sanitization — only use for messages already known to be safe."""
  original_formatters = []
  for h in logger.handlers:
    original_formatters.append(h.formatter)
    h.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)s %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
  logger.log(level, msg, *args)
  for h, fmt in zip(logger.handlers, original_formatters):
    h.setFormatter(fmt)
