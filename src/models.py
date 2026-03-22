from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ProcessingMode(str, Enum):
  LINKS_ONLY = "links_only"
  FULL_CONTENT = "full_content"


class Platform(str, Enum):
  YOUTUBE = "youtube"
  BILIBILI = "bilibili"
  VIMEO = "vimeo"
  TED = "ted"
  WEB = "web"


class ValidationStatus(str, Enum):
  VALID = "valid"
  INVALID_FORMAT = "invalid_format"
  UNREACHABLE = "unreachable"
  RESTRICTED = "restricted"
  UNSUPPORTED = "unsupported"


class SubmitStatus(str, Enum):
  PENDING = "pending"
  SUBMITTED = "submitted"
  FAILED = "failed"


@dataclass
class VideoLink:
  url: str
  normalized_url: str
  platform: Platform
  title: str | None = None
  validation_status: ValidationStatus = ValidationStatus.VALID
  submit_status: SubmitStatus = SubmitStatus.PENDING
  source_id: str | None = None
  error_message: str | None = None


@dataclass
class EmailMessage:
  message_id: str
  sender: str
  subject: str
  body_text: str
  body_html: str | None = None
  received_at: datetime = field(default_factory=datetime.now)
  category: str | None = None
  mode: ProcessingMode = ProcessingMode.LINKS_ONLY
  links: list[VideoLink] = field(default_factory=list)


@dataclass
class ProcessingResult:
  email: EmailMessage
  authorized: bool = True
  mode: ProcessingMode = ProcessingMode.LINKS_ONLY
  content_submitted: bool = False
  content_source_id: str | None = None
  content_error: str | None = None
  links_found: int = 0
  links_valid: int = 0
  links_submitted: int = 0
  links_failed: int = 0
  error_message: str | None = None
  notebook_name: str | None = None
  notebook_id: str | None = None
