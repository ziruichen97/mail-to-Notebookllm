"""Build sanitized reply emails with processing results."""

from __future__ import annotations

import logging
from datetime import datetime

from src.models import ProcessingResult, SubmitStatus, ValidationStatus

logger = logging.getLogger("mail2nlm")


def build_reply_body(result: ProcessingResult) -> str:
  """Compose a human-readable reply summarizing the processing outcome."""
  lines: list[str] = []
  lines.append(f"处理完成！时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
  lines.append("")

  submitted = [l for l in result.email.links if l.submit_status == SubmitStatus.SUBMITTED]
  failed_submit = [l for l in result.email.links if l.submit_status == SubmitStatus.FAILED]
  invalid = [l for l in result.email.links if l.validation_status != ValidationStatus.VALID]

  # Successful links
  if submitted:
    lines.append(f"成功添加 ({len(submitted)} 条)：")
    for i, link in enumerate(submitted, 1):
      lines.append(f"  {i}. [{link.platform.value}] {link.normalized_url}")
      if result.notebook_name:
        lines.append(f"     → Notebook: {result.notebook_name}")
    lines.append("")

  # Failed submissions (link was valid but NotebookLM write failed)
  if failed_submit:
    lines.append(f"提交失败 ({len(failed_submit)} 条)：")
    for i, link in enumerate(failed_submit, 1):
      reason = link.error_message or "未知错误"
      lines.append(f"  {i}. [{link.platform.value}] {link.normalized_url}")
      lines.append(f"     → 原因: {reason}")
    lines.append("")

  # Invalid links (failed validation)
  if invalid:
    lines.append(f"无效链接 ({len(invalid)} 条)：")
    for i, link in enumerate(invalid, 1):
      reason = link.error_message or link.validation_status.value
      lines.append(f"  {i}. {link.url}")
      lines.append(f"     → 原因: {reason}")
    lines.append("")

  # Summary
  lines.append("统计：")
  lines.append(f"  - 总链接数: {result.links_found}")
  lines.append(f"  - 有效: {result.links_valid}")
  lines.append(f"  - 成功提交: {result.links_submitted}")
  lines.append(f"  - 失败: {result.links_failed}")
  if result.notebook_name:
    lines.append(f"  - 目标 Notebook: {result.notebook_name}")

  if result.error_message:
    lines.append("")
    lines.append(f"系统错误: {result.error_message}")

  return "\n".join(lines)
