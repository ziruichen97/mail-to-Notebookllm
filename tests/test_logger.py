"""Tests for log sanitization."""

import pytest

from src.logger import sanitize


class TestSanitize:
  def test_email_masked(self):
    result = sanitize("Sender: user@example.com sent a message")
    assert "user@example.com" not in result
    assert "u***r@example.com" in result

  def test_short_email_masked(self):
    result = sanitize("From: ab@example.com")
    assert "ab@example.com" not in result
    assert "a***@example.com" in result

  def test_youtube_url_masked(self):
    result = sanitize("Processing https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    assert "dQw4w9WgXcQ" not in result
    assert "[YouTube:***]" in result

  def test_bilibili_url_masked(self):
    result = sanitize("Link: https://www.bilibili.com/video/BV1xx411c7mD")
    assert "BV1xx411c7mD" not in result
    assert "[Bilibili:***]" in result

  def test_generic_url_masked(self):
    result = sanitize("Visiting https://www.example.com/private/page")
    assert "private/page" not in result
    assert "[www.example.com:***]" in result

  def test_no_sensitive_data_unchanged(self):
    msg = "Processing 3 links, 2 valid"
    assert sanitize(msg) == msg

  def test_multiple_emails_masked(self):
    result = sanitize("From user@a.com to admin@b.com")
    assert "user@a.com" not in result
    assert "admin@b.com" not in result
