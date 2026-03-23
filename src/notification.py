"""Build sanitized reply emails with processing results."""

from __future__ import annotations

import logging
from datetime import datetime

from src.models import ProcessingMode, ProcessingResult, SubmitStatus, ValidationStatus

logger = logging.getLogger("mail2nlm")


def build_reply_body(result: ProcessingResult) -> str:
  """Compose a human-readable reply summarizing the processing outcome."""
  lines: list[str] = []
  lines.append(f"Processing complete! Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  lines.append("")

  if result.mode == ProcessingMode.FULL_CONTENT:
    lines.append("Mode: Full-content")
    lines.append("")
    if result.content_submitted:
      lines.append("Email content added as text source ✓")
      if result.notebook_name:
        lines.append(f"  → Notebook: {result.notebook_name}")
    else:
      error = result.content_error or "Unknown error"
      lines.append(f"Email content submission failed: {error}")
    lines.append("")

  submitted = [l for l in result.email.links if l.submit_status == SubmitStatus.SUBMITTED]
  failed_submit = [l for l in result.email.links if l.submit_status == SubmitStatus.FAILED]
  invalid = [l for l in result.email.links if l.validation_status != ValidationStatus.VALID]

  if submitted:
    lines.append(f"Links added ({len(submitted)}):")
    for i, link in enumerate(submitted, 1):
      lines.append(f"  {i}. [{link.platform.value}] {link.normalized_url}")
      if result.notebook_name:
        lines.append(f"     → Notebook: {result.notebook_name}")
    lines.append("")

  if failed_submit:
    lines.append(f"Links failed to submit ({len(failed_submit)}):")
    for i, link in enumerate(failed_submit, 1):
      reason = link.error_message or "Unknown error"
      lines.append(f"  {i}. [{link.platform.value}] {link.normalized_url}")
      lines.append(f"     → Reason: {reason}")
    lines.append("")

  if invalid:
    lines.append(f"Invalid links ({len(invalid)}):")
    for i, link in enumerate(invalid, 1):
      reason = link.error_message or link.validation_status.value
      lines.append(f"  {i}. {link.url}")
      lines.append(f"     → Reason: {reason}")
    lines.append("")

  lines.append("Summary:")
  if result.mode == ProcessingMode.FULL_CONTENT:
    lines.append(f"  - Full content: {'submitted' if result.content_submitted else 'failed'}")
  lines.append(f"  - Links found: {result.links_found}")
  if result.links_found > 0:
    lines.append(f"  - Valid: {result.links_valid}")
    lines.append(f"  - Submitted: {result.links_submitted}")
    lines.append(f"  - Failed: {result.links_failed}")
  if result.notebook_name:
    lines.append(f"  - Target Notebook: {result.notebook_name}")

  if result.error_message:
    lines.append("")
    lines.append(f"System error: {result.error_message}")

  return "\n".join(lines)
