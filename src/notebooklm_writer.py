"""NotebookLM integration — Enterprise API and notebooklm-py dual paths."""

from __future__ import annotations

import json
import logging
import os
import tempfile
from abc import ABC, abstractmethod

import httpx

from src.config import NotebookLMConfig
from src.models import Platform, SubmitStatus, VideoLink

logger = logging.getLogger("mail2nlm")


class NotebookLMWriter(ABC):
  """Abstract interface for NotebookLM integration."""

  @abstractmethod
  def ensure_notebook(self, name: str) -> str:
    """Find or create a notebook by name. Returns notebook_id."""
    ...

  @abstractmethod
  def add_sources(self, notebook_id: str, links: list[VideoLink]) -> list[VideoLink]:
    """Add links as sources to a notebook. Updates and returns the links."""
    ...

  @abstractmethod
  def add_text_source(self, notebook_id: str, title: str, content: str) -> str | None:
    """Add raw text as a source. Returns source_id or None on failure."""
    ...


# ---------------------------------------------------------------------------
# Enterprise API implementation
# ---------------------------------------------------------------------------

class EnterpriseAPIWriter(NotebookLMWriter):
  """Uses the official NotebookLM Enterprise REST API."""

  def __init__(self, config: NotebookLMConfig):
    self.config = config
    self.base_url = (
      f"https://{config.endpoint_location}-discoveryengine.googleapis.com"
      f"/v1alpha/projects/{config.project_number}/locations/{config.location}"
    )
    self._access_token: str | None = None

  def _get_access_token(self) -> str:
    if self._access_token:
      return self._access_token

    try:
      from google.auth.transport.requests import Request
      from google.oauth2 import service_account

      creds_json = self.config.credentials_json
      if not creds_json:
        raise ValueError("GCP_CREDENTIALS_JSON not set")

      # Write credentials to a temp file if provided as JSON string
      if creds_json.strip().startswith("{"):
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(creds_json)
        tmp.close()
        creds_path = tmp.name
      else:
        creds_path = creds_json

      creds = service_account.Credentials.from_service_account_file(
        creds_path,
        scopes=["https://www.googleapis.com/auth/cloud-platform"],
      )
      creds.refresh(Request())
      self._access_token = creds.token

      if creds_json.strip().startswith("{"):
        os.unlink(creds_path)

      return self._access_token
    except ImportError:
      raise RuntimeError(
        "google-auth is required for Enterprise API. "
        "Install with: pip install google-auth"
      )

  def _headers(self) -> dict[str, str]:
    return {
      "Authorization": f"Bearer {self._get_access_token()}",
      "Content-Type": "application/json",
    }

  def ensure_notebook(self, name: str) -> str:
    url = f"{self.base_url}/notebooks"

    try:
      with httpx.Client(timeout=30) as client:
        # List existing notebooks and find by name
        resp = client.get(url, headers=self._headers())
        resp.raise_for_status()
        notebooks = resp.json().get("notebooks", [])

        for nb in notebooks:
          if nb.get("displayName") == name:
            nb_id = nb["name"].split("/")[-1]
            logger.info("Found existing notebook: %s", name)
            return nb_id

        # Create new notebook
        resp = client.post(url, headers=self._headers(), json={"displayName": name})
        resp.raise_for_status()
        nb_id = resp.json()["name"].split("/")[-1]
        logger.info("Created new notebook: %s", name)
        return nb_id
    except Exception:
      logger.exception("Failed to ensure notebook")
      raise

  def add_sources(self, notebook_id: str, links: list[VideoLink]) -> list[VideoLink]:
    url = f"{self.base_url}/notebooks/{notebook_id}/sources:batchCreate"

    user_contents = []
    for link in links:
      if link.platform == Platform.YOUTUBE:
        user_contents.append({"videoContent": {"youtubeUrl": link.normalized_url}})
      else:
        source_name = f"{link.platform.value} - {link.normalized_url}"
        user_contents.append({
          "webContent": {"url": link.normalized_url, "sourceName": source_name}
        })

    try:
      with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=self._headers(), json={"userContents": user_contents})
        resp.raise_for_status()
        result = resp.json()

      sources = result.get("sources", [])
      for i, link in enumerate(links):
        if i < len(sources):
          link.source_id = sources[i].get("sourceId", {}).get("id")
          link.submit_status = SubmitStatus.SUBMITTED
        else:
          link.submit_status = SubmitStatus.FAILED
          link.error_message = "No source ID in response"

      logger.info("Submitted %d source(s) via Enterprise API", len(sources))
    except Exception as exc:
      logger.exception("Enterprise API source submission failed")
      for link in links:
        link.submit_status = SubmitStatus.FAILED
        link.error_message = str(type(exc).__name__)

    return links

  def add_text_source(self, notebook_id: str, title: str, content: str) -> str | None:
    url = f"{self.base_url}/notebooks/{notebook_id}/sources:batchCreate"
    payload = {
      "userContents": [{
        "textContent": {"sourceName": title, "content": content}
      }]
    }
    try:
      with httpx.Client(timeout=60) as client:
        resp = client.post(url, headers=self._headers(), json=payload)
        resp.raise_for_status()
        result = resp.json()
      sources = result.get("sources", [])
      if sources:
        source_id = sources[0].get("sourceId", {}).get("id")
        logger.info("Text source submitted via Enterprise API")
        return source_id
      return None
    except Exception:
      logger.exception("Enterprise API text source submission failed")
      return None


# ---------------------------------------------------------------------------
# notebooklm-py implementation
# ---------------------------------------------------------------------------

class NotebookLMPyWriter(NotebookLMWriter):
  """Uses the unofficial notebooklm-py library."""

  def __init__(self, config: NotebookLMConfig):
    self.config = config
    self._client = None

    if config.auth_json:
      os.environ.setdefault("NOTEBOOKLM_AUTH_JSON", config.auth_json)

  def _get_client(self):
    if self._client is not None:
      return self._client

    try:
      from notebooklm import NotebookLM
      self._client = NotebookLM()
      return self._client
    except ImportError:
      raise RuntimeError(
        "notebooklm-py is required. Install with: pip install notebooklm-py"
      )

  def ensure_notebook(self, name: str) -> str:
    client = self._get_client()
    try:
      notebooks = client.list_notebooks()
      for nb in notebooks:
        nb_name = getattr(nb, "title", None) or getattr(nb, "name", "")
        if nb_name == name:
          nb_id = getattr(nb, "id", None) or getattr(nb, "notebook_id", str(nb))
          logger.info("Found existing notebook: %s", name)
          return str(nb_id)

      nb = client.create_notebook(name)
      nb_id = getattr(nb, "id", None) or getattr(nb, "notebook_id", str(nb))
      logger.info("Created new notebook: %s", name)
      return str(nb_id)
    except Exception:
      logger.exception("Failed to ensure notebook via notebooklm-py")
      raise

  def add_sources(self, notebook_id: str, links: list[VideoLink]) -> list[VideoLink]:
    client = self._get_client()

    for link in links:
      try:
        if link.platform == Platform.YOUTUBE:
          source = client.add_youtube_source(notebook_id, link.normalized_url)
        else:
          source = client.add_url_source(notebook_id, link.normalized_url)

        link.source_id = getattr(source, "id", None) or str(source)
        link.submit_status = SubmitStatus.SUBMITTED
      except Exception as exc:
        link.submit_status = SubmitStatus.FAILED
        link.error_message = type(exc).__name__
        logger.warning("Failed to add source for link on %s", link.platform.value)

    submitted = sum(1 for l in links if l.submit_status == SubmitStatus.SUBMITTED)
    logger.info("Submitted %d/%d source(s) via notebooklm-py", submitted, len(links))
    return links

  def add_text_source(self, notebook_id: str, title: str, content: str) -> str | None:
    client = self._get_client()
    try:
      source = client.add_text_source(notebook_id, content, title=title)
      source_id = getattr(source, "id", None) or str(source)
      logger.info("Text source submitted via notebooklm-py")
      return source_id
    except Exception:
      logger.exception("Failed to add text source via notebooklm-py")
      return None


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_writer(config: NotebookLMConfig) -> NotebookLMWriter:
  if config.integration == "enterprise_api":
    logger.info("Using NotebookLM Enterprise API")
    return EnterpriseAPIWriter(config)
  else:
    logger.info("Using notebooklm-py (unofficial)")
    return NotebookLMPyWriter(config)
