"""Configuration loading from YAML + environment variables."""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class ImapConfig(BaseModel):
  host: str = "imap.gmail.com"
  port: int = 993
  use_ssl: bool = True


class SmtpConfig(BaseModel):
  host: str = "smtp.gmail.com"
  port: int = 587
  use_tls: bool = True


class EmailConfig(BaseModel):
  imap: ImapConfig = Field(default_factory=ImapConfig)
  smtp: SmtpConfig = Field(default_factory=SmtpConfig)
  username: str = ""
  password: str = ""
  folder: str = "INBOX"


class AuthConfig(BaseModel):
  allowed_senders: list[str] = Field(default_factory=list)
  require_subject_key: bool = False
  subject_key: str = ""
  check_spf_dkim: bool = False


class LinkProcessingConfig(BaseModel):
  supported_platforms: list[str] = Field(
    default_factory=lambda: ["youtube", "bilibili", "vimeo", "ted"]
  )
  allow_generic_urls: bool = False
  validation_timeout: int = 10
  max_retries: int = 2
  expand_short_urls: bool = True


class NotebookLMConfig(BaseModel):
  integration: str = "notebooklm_py"
  project_number: str = ""
  location: str = "us"
  endpoint_location: str = "us"
  credentials_json: str = ""
  auth_json: str = ""
  default_category: str = "monthly"
  max_sources_per_notebook: int = 280


class NotificationConfig(BaseModel):
  send_reply: bool = True


class ClassificationConfig(BaseModel):
  strategy: str = "user_specified"


class AppConfig(BaseModel):
  email: EmailConfig = Field(default_factory=EmailConfig)
  auth: AuthConfig = Field(default_factory=AuthConfig)
  link_processing: LinkProcessingConfig = Field(default_factory=LinkProcessingConfig)
  notebooklm: NotebookLMConfig = Field(default_factory=NotebookLMConfig)
  notification: NotificationConfig = Field(default_factory=NotificationConfig)
  classification: ClassificationConfig = Field(default_factory=ClassificationConfig)


def _resolve_env(value: str) -> str:
  """Replace ${VAR} placeholders with environment variable values."""
  if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
    env_key = value[2:-1]
    return os.environ.get(env_key, "")
  return value


def _resolve_env_recursive(obj: dict | list | str) -> dict | list | str:
  if isinstance(obj, dict):
    return {k: _resolve_env_recursive(v) for k, v in obj.items()}
  if isinstance(obj, list):
    return [_resolve_env_recursive(item) for item in obj]
  if isinstance(obj, str):
    return _resolve_env(obj)
  return obj


def load_config(config_path: str | Path | None = None) -> AppConfig:
  """Load configuration from YAML file, then overlay environment variables."""
  raw: dict = {}

  if config_path and Path(config_path).exists():
    with open(config_path) as f:
      raw = yaml.safe_load(f) or {}

  raw = _resolve_env_recursive(raw)

  config = AppConfig(**raw) if raw else AppConfig()

  # Environment variable overrides (highest priority)
  if v := os.environ.get("EMAIL_USERNAME"):
    config.email.username = v
  if v := os.environ.get("EMAIL_PASSWORD"):
    config.email.password = v
  if v := os.environ.get("EMAIL_IMAP_HOST"):
    config.email.imap.host = v
  if v := os.environ.get("EMAIL_IMAP_PORT"):
    config.email.imap.port = int(v)
  if v := os.environ.get("EMAIL_SMTP_HOST"):
    config.email.smtp.host = v
  if v := os.environ.get("EMAIL_SMTP_PORT"):
    config.email.smtp.port = int(v)
  if v := os.environ.get("AUTH_SUBJECT_KEY"):
    config.auth.subject_key = v
  if v := os.environ.get("AUTH_ALLOWED_SENDERS"):
    config.auth.allowed_senders = [s.strip() for s in v.split(",") if s.strip()]
  if v := os.environ.get("GCP_PROJECT_NUMBER"):
    config.notebooklm.project_number = v
  if v := os.environ.get("GCP_CREDENTIALS_JSON"):
    config.notebooklm.credentials_json = v
  if v := os.environ.get("NOTEBOOKLM_AUTH_JSON"):
    config.notebooklm.auth_json = v
  if v := os.environ.get("NOTEBOOKLM_INTEGRATION"):
    config.notebooklm.integration = v
  if v := os.environ.get("NOTEBOOKLM_LOCATION"):
    config.notebooklm.location = v
    config.notebooklm.endpoint_location = v
  if v := os.environ.get("DEFAULT_CATEGORY"):
    config.notebooklm.default_category = v

  return config
