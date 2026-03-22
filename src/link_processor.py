"""Extract, normalize, and deduplicate video links from email content."""

from __future__ import annotations

import logging
import re
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from src.models import Platform, ProcessingMode, VideoLink

logger = logging.getLogger("mail2nlm")

_GENERIC_URL_RE = re.compile(r"https?://[^\s<>\"')\]\},]+")

_PLATFORM_PATTERNS: dict[Platform, list[re.Pattern]] = {
  Platform.YOUTUBE: [
    re.compile(r"https?://(?:www\.)?youtube\.com/watch\?[^\s<>\"')\]]*v=([\w-]{11})"),
    re.compile(r"https?://youtu\.be/([\w-]{11})"),
    re.compile(r"https?://(?:www\.)?youtube\.com/shorts/([\w-]{11})"),
    re.compile(r"https?://(?:www\.)?youtube\.com/live/([\w-]{11})"),
  ],
  Platform.BILIBILI: [
    re.compile(r"https?://(?:www\.)?bilibili\.com/video/(BV[\w]+)"),
    re.compile(r"https?://b23\.tv/([\w]+)"),
  ],
  Platform.VIMEO: [
    re.compile(r"https?://(?:www\.)?vimeo\.com/(\d+)"),
  ],
  Platform.TED: [
    re.compile(r"https?://(?:www\.)?ted\.com/talks/([\w_]+)"),
  ],
}

_DOMAIN_TO_PLATFORM: dict[str, Platform] = {
  "youtube.com": Platform.YOUTUBE,
  "www.youtube.com": Platform.YOUTUBE,
  "youtu.be": Platform.YOUTUBE,
  "bilibili.com": Platform.BILIBILI,
  "www.bilibili.com": Platform.BILIBILI,
  "b23.tv": Platform.BILIBILI,
  "vimeo.com": Platform.VIMEO,
  "www.vimeo.com": Platform.VIMEO,
  "ted.com": Platform.TED,
  "www.ted.com": Platform.TED,
}


def _extract_urls_from_text(text: str) -> list[str]:
  return _GENERIC_URL_RE.findall(text)


def _extract_urls_from_html(html: str) -> list[str]:
  urls: list[str] = []
  try:
    soup = BeautifulSoup(html, "html.parser")
    for a_tag in soup.find_all("a", href=True):
      href = a_tag["href"]
      if href.startswith("http"):
        urls.append(href)
    # Also extract URLs from visible text (in case links are plain text)
    text = soup.get_text(separator=" ")
    urls.extend(_extract_urls_from_text(text))
  except Exception:
    logger.debug("HTML parsing failed, falling back to regex")
    urls.extend(_extract_urls_from_text(html))
  return urls


def _detect_platform(url: str) -> Platform | None:
  try:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return _DOMAIN_TO_PLATFORM.get(host)
  except Exception:
    return None


def _normalize_url(url: str, platform: Platform) -> str:
  """Normalize URL to a canonical form for deduplication."""
  try:
    parsed = urlparse(url)

    if platform == Platform.YOUTUBE:
      # All YouTube URLs → https://www.youtube.com/watch?v=VIDEO_ID
      for pattern in _PLATFORM_PATTERNS[Platform.YOUTUBE]:
        m = pattern.search(url)
        if m:
          video_id = m.group(1)
          return f"https://www.youtube.com/watch?v={video_id}"

      qs = parse_qs(parsed.query)
      if "v" in qs:
        return f"https://www.youtube.com/watch?v={qs['v'][0]}"

    if platform == Platform.BILIBILI:
      for pattern in _PLATFORM_PATTERNS[Platform.BILIBILI]:
        m = pattern.search(url)
        if m:
          bv_id = m.group(1)
          if bv_id.startswith("BV"):
            return f"https://www.bilibili.com/video/{bv_id}"

    # Strip trailing slashes and fragments for generic normalization
    clean = url.split("#")[0].rstrip("/")
    return clean

  except Exception:
    return url


def extract_links(
  body_text: str,
  body_html: str | None,
  supported_platforms: list[str],
  allow_generic: bool = False,
) -> list[VideoLink]:
  """Extract and deduplicate video links from email body."""

  raw_urls: list[str] = []
  raw_urls.extend(_extract_urls_from_text(body_text))
  if body_html:
    raw_urls.extend(_extract_urls_from_html(body_html))

  seen_normalized: set[str] = set()
  results: list[VideoLink] = []

  for url in raw_urls:
    url = url.strip().rstrip(".,;:!?")
    if not url.startswith("http"):
      continue

    platform = _detect_platform(url)

    if platform is None:
      if allow_generic:
        platform = Platform.WEB
      else:
        continue

    if platform.value not in supported_platforms and platform != Platform.WEB:
      continue

    normalized = _normalize_url(url, platform)
    if normalized in seen_normalized:
      continue
    seen_normalized.add(normalized)

    results.append(VideoLink(url=url, normalized_url=normalized, platform=platform))

  logger.info("Extracted %d unique link(s) from email body", len(results))
  return results


def extract_category(subject: str) -> str | None:
  """Extract category tag from email subject: '[机器学习] ...' → '机器学习'."""
  m = re.search(r"\[([^\]]+)\]", subject)
  if m:
    category = m.group(1).strip()
    if category:
      logger.info("Category extracted from subject: %s", category)
      return category
  return None


# Full-content mode triggers
_FULL_CONTENT_TAGS = ("文章", "全文", "article", "full")
_FORWARD_PREFIXES = ("fwd:", "fw:", "转发:", "转发：")


def detect_mode(subject: str) -> tuple[ProcessingMode, str | None]:
  """Detect processing mode and category from subject line.

  Patterns:
    [文章]           → full_content, no category
    [文章:机器学习]  → full_content, category = "机器学习"
    Fwd: / 转发:     → full_content, no category
    [机器学习]       → links_only, category = "机器学习"
    (no tag)         → links_only, no category
  """
  # Check for [文章] or [文章:分类] tag
  m = re.search(r"\[([^\]]+)\]", subject)
  if m:
    tag = m.group(1).strip()
    # "[文章:分类名]" pattern
    if ":" in tag or "：" in tag:
      parts = re.split(r"[:：]", tag, maxsplit=1)
      prefix = parts[0].strip().lower()
      if prefix in _FULL_CONTENT_TAGS:
        category = parts[1].strip() if len(parts) > 1 and parts[1].strip() else None
        logger.info("Full-content mode (tagged with category)")
        return ProcessingMode.FULL_CONTENT, category
    # "[文章]" alone
    elif tag.lower() in _FULL_CONTENT_TAGS:
      logger.info("Full-content mode (tagged)")
      return ProcessingMode.FULL_CONTENT, None

  # Check for forwarded email prefixes
  subject_lower = subject.lower().strip()
  for prefix in _FORWARD_PREFIXES:
    if subject_lower.startswith(prefix):
      logger.info("Full-content mode (forwarded email detected)")
      return ProcessingMode.FULL_CONTENT, None

  # Default: links-only mode, extract category normally
  category = extract_category(subject)
  return ProcessingMode.LINKS_ONLY, category


def prepare_text_content(body_text: str, body_html: str | None, subject: str) -> str:
  """Prepare email body for submission as a text source to NotebookLM.

  Prefers HTML-to-text conversion for richer structure, falls back to plain text.
  Prepends the subject as a title.
  """
  content_parts: list[str] = [subject, "", "---", ""]

  if body_html:
    try:
      soup = BeautifulSoup(body_html, "html.parser")
      # Remove script/style elements
      for tag in soup(["script", "style"]):
        tag.decompose()
      text = soup.get_text(separator="\n")
      # Collapse excessive blank lines
      lines = [line.strip() for line in text.splitlines()]
      text = "\n".join(line for i, line in enumerate(lines)
                       if line or (i > 0 and lines[i - 1]))
      if text.strip():
        content_parts.append(text.strip())
      else:
        content_parts.append(body_text)
    except Exception:
      content_parts.append(body_text)
  else:
    content_parts.append(body_text)

  return "\n".join(content_parts)
