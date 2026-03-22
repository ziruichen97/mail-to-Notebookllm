"""Tests for link extraction and normalization."""

import pytest

from src.link_processor import extract_category, extract_links
from src.models import Platform


ALL_PLATFORMS = ["youtube", "bilibili", "vimeo", "ted"]


class TestExtractLinks:
  def test_youtube_standard(self):
    text = "Check this out: https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    links = extract_links(text, None, ALL_PLATFORMS)
    assert len(links) == 1
    assert links[0].platform == Platform.YOUTUBE
    assert links[0].normalized_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

  def test_youtube_short(self):
    text = "https://youtu.be/dQw4w9WgXcQ"
    links = extract_links(text, None, ALL_PLATFORMS)
    assert len(links) == 1
    assert links[0].platform == Platform.YOUTUBE
    assert links[0].normalized_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

  def test_youtube_shorts(self):
    text = "https://youtube.com/shorts/dQw4w9WgXcQ"
    links = extract_links(text, None, ALL_PLATFORMS)
    assert len(links) == 1
    assert links[0].normalized_url == "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

  def test_bilibili(self):
    text = "https://www.bilibili.com/video/BV1xx411c7mD"
    links = extract_links(text, None, ALL_PLATFORMS)
    assert len(links) == 1
    assert links[0].platform == Platform.BILIBILI
    assert "BV1xx411c7mD" in links[0].normalized_url

  def test_vimeo(self):
    text = "https://vimeo.com/123456789"
    links = extract_links(text, None, ALL_PLATFORMS)
    assert len(links) == 1
    assert links[0].platform == Platform.VIMEO

  def test_ted(self):
    text = "https://www.ted.com/talks/some_speaker_title"
    links = extract_links(text, None, ALL_PLATFORMS)
    assert len(links) == 1
    assert links[0].platform == Platform.TED

  def test_multiple_links(self):
    text = """Here are some videos:
    https://youtube.com/watch?v=dQw4w9WgXcQ
    https://www.bilibili.com/video/BV1xx411c7mD
    https://vimeo.com/123456789
    """
    links = extract_links(text, None, ALL_PLATFORMS)
    assert len(links) == 3

  def test_deduplication(self):
    text = """
    https://youtube.com/watch?v=dQw4w9WgXcQ
    https://youtu.be/dQw4w9WgXcQ
    https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PLxyz
    """
    links = extract_links(text, None, ALL_PLATFORMS)
    assert len(links) == 1

  def test_html_href_extraction(self):
    html = '<a href="https://youtube.com/watch?v=dQw4w9WgXcQ">Watch</a>'
    links = extract_links("", html, ALL_PLATFORMS)
    assert len(links) == 1
    assert links[0].platform == Platform.YOUTUBE

  def test_unsupported_platform_ignored(self):
    text = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    links = extract_links(text, None, ["bilibili"])
    assert len(links) == 0

  def test_generic_url_disabled(self):
    text = "https://www.example.com/some-page"
    links = extract_links(text, None, ALL_PLATFORMS, allow_generic=False)
    assert len(links) == 0

  def test_generic_url_enabled(self):
    text = "https://www.example.com/some-page"
    links = extract_links(text, None, ALL_PLATFORMS, allow_generic=True)
    assert len(links) == 1
    assert links[0].platform == Platform.WEB

  def test_empty_body(self):
    links = extract_links("", None, ALL_PLATFORMS)
    assert len(links) == 0

  def test_no_urls(self):
    links = extract_links("Just a regular email with no links.", None, ALL_PLATFORMS)
    assert len(links) == 0


class TestExtractCategory:
  def test_bracket_tag(self):
    assert extract_category("[机器学习] 最新的 Transformer 教程") == "机器学习"

  def test_english_tag(self):
    assert extract_category("[Deep Learning] New video") == "Deep Learning"

  def test_no_tag(self):
    assert extract_category("Just a normal subject") is None

  def test_empty_brackets(self):
    assert extract_category("[] empty tag") is None

  def test_multiple_tags_takes_first(self):
    result = extract_category("[Tag1] text [Tag2] more")
    assert result == "Tag1"
