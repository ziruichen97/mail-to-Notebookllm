"""Validate extracted links — format check + HTTP reachability."""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import httpx

from src.models import ValidationStatus, VideoLink

logger = logging.getLogger("mail2nlm")

_PRIVATE_IP_PREFIXES = ("10.", "172.16.", "172.17.", "172.18.", "172.19.",
                         "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
                         "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
                         "172.30.", "172.31.", "192.168.", "127.", "0.")


def _is_safe_url(url: str) -> bool:
  """Block private IPs and non-HTTP schemes (SSRF prevention)."""
  try:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
      return False
    host = parsed.hostname or ""
    if host == "localhost" or any(host.startswith(p) for p in _PRIVATE_IP_PREFIXES):
      return False
    return True
  except Exception:
    return False


def validate_link(link: VideoLink, timeout: int = 10, max_retries: int = 2) -> VideoLink:
  """Validate a single link: format → safety → HTTP reachability."""

  if not link.normalized_url.startswith("http"):
    link.validation_status = ValidationStatus.INVALID_FORMAT
    link.error_message = "URL does not start with http(s)"
    return link

  if not _is_safe_url(link.normalized_url):
    link.validation_status = ValidationStatus.INVALID_FORMAT
    link.error_message = "URL points to a restricted address"
    return link

  for attempt in range(1, max_retries + 1):
    try:
      with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.head(link.normalized_url, headers={
          "User-Agent": "Mozilla/5.0 (compatible; Mail2NLM/1.0)"
        })

      if resp.status_code < 400:
        link.validation_status = ValidationStatus.VALID
        link.error_message = None
        return link

      if resp.status_code == 403:
        link.validation_status = ValidationStatus.RESTRICTED
        link.error_message = f"HTTP {resp.status_code} — access restricted"
        return link

      if resp.status_code >= 400:
        link.validation_status = ValidationStatus.UNREACHABLE
        link.error_message = f"HTTP {resp.status_code}"

    except httpx.TimeoutException:
      link.validation_status = ValidationStatus.UNREACHABLE
      link.error_message = f"Timeout after {timeout}s (attempt {attempt}/{max_retries})"
    except httpx.HTTPError as exc:
      link.validation_status = ValidationStatus.UNREACHABLE
      link.error_message = f"HTTP error: {type(exc).__name__}"
    except Exception as exc:
      link.validation_status = ValidationStatus.UNREACHABLE
      link.error_message = f"Unexpected error: {type(exc).__name__}"

  return link


def validate_links(
  links: list[VideoLink],
  timeout: int = 10,
  max_retries: int = 2,
) -> tuple[list[VideoLink], list[VideoLink]]:
  """Validate all links, returning (valid, invalid) lists."""
  valid: list[VideoLink] = []
  invalid: list[VideoLink] = []

  for link in links:
    validate_link(link, timeout=timeout, max_retries=max_retries)
    if link.validation_status == ValidationStatus.VALID:
      valid.append(link)
    else:
      invalid.append(link)

  logger.info(
    "Validation complete: %d valid, %d invalid out of %d total",
    len(valid), len(invalid), len(links),
  )
  return valid, invalid
