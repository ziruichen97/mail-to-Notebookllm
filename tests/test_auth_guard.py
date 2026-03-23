"""Tests for sender authorization."""

import pytest

from src.auth_guard import check_subject_key, is_authorized
from src.config import AuthConfig


class TestIsAuthorized:
  def test_exact_match(self):
    cfg = AuthConfig(allowed_senders=["user@example.com"])
    assert is_authorized("user@example.com", cfg) is True

  def test_case_insensitive(self):
    cfg = AuthConfig(allowed_senders=["User@Example.COM"])
    assert is_authorized("user@example.com", cfg) is True

  def test_display_name_stripped(self):
    cfg = AuthConfig(allowed_senders=["user@example.com"])
    assert is_authorized("John Doe <user@example.com>", cfg) is True

  def test_wildcard_domain(self):
    cfg = AuthConfig(allowed_senders=["*@example.com"])
    assert is_authorized("anyone@example.com", cfg) is True

  def test_rejected_sender(self):
    cfg = AuthConfig(allowed_senders=["allowed@example.com"])
    assert is_authorized("stranger@evil.com", cfg) is False

  def test_empty_whitelist_rejects_all(self):
    cfg = AuthConfig(allowed_senders=[])
    assert is_authorized("user@example.com", cfg) is False

  def test_multiple_patterns(self):
    cfg = AuthConfig(allowed_senders=["admin@site.com", "*@trusted.org"])
    assert is_authorized("admin@site.com", cfg) is True
    assert is_authorized("anyone@trusted.org", cfg) is True
    assert is_authorized("hacker@bad.com", cfg) is False


class TestCheckSubjectKey:
  def test_key_not_required(self):
    cfg = AuthConfig(require_subject_key=False)
    assert check_subject_key("any subject", cfg) is True

  def test_key_present(self):
    cfg = AuthConfig(require_subject_key=True, subject_key="secret123")
    assert check_subject_key("[ML] secret123 new videos", cfg) is True

  def test_key_missing(self):
    cfg = AuthConfig(require_subject_key=True, subject_key="secret123")
    assert check_subject_key("[ML] new videos", cfg) is False

  def test_key_required_but_not_configured(self):
    cfg = AuthConfig(require_subject_key=True, subject_key="")
    assert check_subject_key("anything", cfg) is False
