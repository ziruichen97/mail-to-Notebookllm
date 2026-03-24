"""Tests for IMAP client ID (Netease / RFC 2971)."""

from unittest.mock import MagicMock

from src.config import EmailConfig, ImapConfig
from src.email_client import _default_imap_client_id, _send_imap_client_id


class TestDefaultImapClientId:
  def test_support_email_from_username(self):
    d = _default_imap_client_id("bot@163.com")
    assert d["support-email"] == "bot@163.com"
    assert d["name"] == "MailToNotebookLM"
    assert "version" in d and "vendor" in d

  def test_fallback_when_no_at(self):
    d = _default_imap_client_id("nousername")
    assert d["support-email"] == "noreply@localhost"


class TestSendImapClientId:
  def test_skips_when_disabled(self):
    client = MagicMock()
    cfg = EmailConfig(
      imap=ImapConfig(send_client_id=False),
      username="u@example.com",
      password="x",
    )
    _send_imap_client_id(client, cfg)
    client.id_.assert_not_called()

  def test_calls_id_with_defaults(self):
    client = MagicMock()
    cfg = EmailConfig(
      imap=ImapConfig(send_client_id=True),
      username="u@example.com",
      password="x",
    )
    _send_imap_client_id(client, cfg)
    client.id_.assert_called_once()
    args = client.id_.call_args[0][0]
    assert args["support-email"] == "u@example.com"

  def test_custom_client_id_override(self):
    client = MagicMock()
    custom = {"name": "Custom", "version": "2.0", "vendor": "v", "support-email": "a@b.com"}
    cfg = EmailConfig(
      imap=ImapConfig(send_client_id=True, client_id=custom),
      username="u@example.com",
      password="x",
    )
    _send_imap_client_id(client, cfg)
    client.id_.assert_called_once_with(custom)
