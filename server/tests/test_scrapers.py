"""Unit and integration tests for scrapers package."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scrapers import detect_scraper
from scrapers.base import html_clean, write_chapter
from scrapers.truyenfull import (
    TruyenfullScraper,
    _parse_chapter_content,
    _parse_chapter_list,
)
from scrapers.zingtruyen import (
    ZingtruyenScraper,
    _parse_group_page,
    _parse_group_urls,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# scrapers/base.py
# ---------------------------------------------------------------------------

def test_html_clean_strips_tags():
    assert html_clean("<b>Hello</b> <i>World</i>") == "Hello World"


def test_html_clean_unescapes_entities():
    assert html_clean("&amp; &lt;tag&gt;") == "& <tag>"


def test_html_clean_empty():
    assert html_clean("") == ""


def test_html_clean_nested_tags():
    assert html_clean("<div><p>text</p></div>") == "text"


def test_write_chapter_creates_file(tmp_path):
    path = write_chapter(1, "Chương 1: Test", "Nội dung test.", tmp_path)
    assert path.exists()
    assert path.read_text(encoding="utf-8") == "# Chương 1: Test\n\nNội dung test.\n"


def test_write_chapter_zero_pads_filename(tmp_path):
    assert write_chapter(42, "T", "B", tmp_path).name == "ch_042.md"


def test_write_chapter_creates_parent_dir(tmp_path):
    dest = tmp_path / "new_subdir"
    write_chapter(1, "T", "B", dest)
    assert dest.exists()


# ---------------------------------------------------------------------------
# scrapers/truyenfull.py — parsers
# ---------------------------------------------------------------------------

def test_parse_chapter_list_extracts_links():
    html = (FIXTURES / "truyenfull_listing.html").read_text(encoding="utf-8")
    chapters = _parse_chapter_list(html, "test-book")
    assert len(chapters) == 2
    assert chapters[0]["url"] == "https://truyenfull.vision/test-book/chuong-1/"
    assert "Khởi Đầu" in chapters[0]["title"]


def test_parse_chapter_list_wrong_slug_returns_empty():
    html = (FIXTURES / "truyenfull_listing.html").read_text(encoding="utf-8")
    assert _parse_chapter_list(html, "other-book") == []


def test_parse_chapter_content_extracts_title():
    html = (FIXTURES / "truyenfull_chapter.html").read_text(encoding="utf-8")
    title, _ = _parse_chapter_content(html)
    assert "Khởi Đầu" in title


def test_parse_chapter_content_extracts_body():
    html = (FIXTURES / "truyenfull_chapter.html").read_text(encoding="utf-8")
    _, body = _parse_chapter_content(html)
    assert "đoạn đầu tiên" in body
    assert "đoạn thứ hai" in body


def test_parse_chapter_content_no_html_in_body():
    html = (FIXTURES / "truyenfull_chapter.html").read_text(encoding="utf-8")
    _, body = _parse_chapter_content(html)
    assert "<" not in body
    assert "chapter-nav" not in body


def test_parse_chapter_content_empty_html_fallback():
    title, body = _parse_chapter_content("<html></html>")
    assert title == "Không rõ tiêu đề"
    assert body == ""


# ---------------------------------------------------------------------------
# scrapers/zingtruyen.py — parsers
# ---------------------------------------------------------------------------

def test_parse_group_urls_extracts_url():
    html = (FIXTURES / "zingtruyen_listing.html").read_text(encoding="utf-8")
    urls = _parse_group_urls(html)
    assert len(urls) == 1
    assert "chuong-1-50" in urls[0]


def test_parse_group_urls_deduplicates():
    html = (FIXTURES / "zingtruyen_listing.html").read_text(encoding="utf-8")
    doubled = html.replace("</div>", html + "</div>", 1)
    urls = _parse_group_urls(doubled)
    assert len(urls) == len(set(urls))


def test_parse_group_urls_empty_html():
    assert _parse_group_urls("<html></html>") == []


def test_parse_group_page_extracts_both_chapters():
    html = (FIXTURES / "zingtruyen_group.html").read_text(encoding="utf-8")
    chapters = _parse_group_page(html)
    assert 1 in chapters
    assert 2 in chapters


def test_parse_group_page_title_format():
    html = (FIXTURES / "zingtruyen_group.html").read_text(encoding="utf-8")
    title, _ = _parse_group_page(html)[1]
    assert title.startswith("Chương 1:")


def test_parse_group_page_body_has_content():
    html = (FIXTURES / "zingtruyen_group.html").read_text(encoding="utf-8")
    _, body = _parse_group_page(html)[1]
    assert "đoạn đầu tiên" in body


def test_parse_group_page_no_html_in_body():
    html = (FIXTURES / "zingtruyen_group.html").read_text(encoding="utf-8")
    for _, (_, body) in _parse_group_page(html).items():
        assert "<" not in body


def test_parse_group_page_nav_not_in_body():
    html = (FIXTURES / "zingtruyen_group.html").read_text(encoding="utf-8")
    for _, (_, body) in _parse_group_page(html).items():
        assert "Trước" not in body
        assert "Sau" not in body


def test_parse_group_page_missing_content_div():
    assert _parse_group_page("<html></html>") == {}


# ---------------------------------------------------------------------------
# scrapers/__init__.py — factory
# ---------------------------------------------------------------------------

def test_detect_scraper_truyenfull():
    assert isinstance(detect_scraper("https://truyenfull.vision/some-book/"), TruyenfullScraper)


def test_detect_scraper_zingtruyen():
    assert isinstance(
        detect_scraper("https://zingtruyen.store/story/some-book/123.html"),
        ZingtruyenScraper,
    )


def test_detect_scraper_unknown_raises():
    with pytest.raises(ValueError, match="Unsupported"):
        detect_scraper("https://unknown-site.com/book")


# ---------------------------------------------------------------------------
# TruyenfullScraper.scrape — integration (mocked HTTP)
# ---------------------------------------------------------------------------

def _resp(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def test_truyenfull_scraper_downloads_all_chapters(tmp_path):
    listing = (FIXTURES / "truyenfull_listing.html").read_text(encoding="utf-8")
    chapter = (FIXTURES / "truyenfull_chapter.html").read_text(encoding="utf-8")

    def fake_get(session, url, **kw):
        if "trang-1" in url:
            return _resp(listing)
        if "trang-" in url:
            return _resp("<html></html>")
        return _resp(chapter)

    with patch("scrapers.truyenfull.polite_get", side_effect=fake_get), \
         patch("scrapers.truyenfull.make_session", return_value=MagicMock()):
        count = TruyenfullScraper().scrape(
            "https://truyenfull.vision/test-book/", tmp_path
        )

    assert count == 2
    assert (tmp_path / "ch_001.md").exists()
    assert (tmp_path / "ch_002.md").exists()


def test_truyenfull_scraper_skips_existing_files(tmp_path):
    listing = (FIXTURES / "truyenfull_listing.html").read_text(encoding="utf-8")
    chapter = (FIXTURES / "truyenfull_chapter.html").read_text(encoding="utf-8")
    (tmp_path / "ch_001.md").write_text("existing", encoding="utf-8")
    fetched_urls = []

    def fake_get(session, url, **kw):
        fetched_urls.append(url)
        if "trang-1" in url:
            return _resp(listing)
        if "trang-" in url:
            return _resp("<html></html>")
        return _resp(chapter)

    with patch("scrapers.truyenfull.polite_get", side_effect=fake_get), \
         patch("scrapers.truyenfull.make_session", return_value=MagicMock()):
        TruyenfullScraper().scrape("https://truyenfull.vision/test-book/", tmp_path)

    chapter_fetches = [u for u in fetched_urls if "chuong-" in u]
    assert len(chapter_fetches) == 1  # only ch_002 fetched


def test_truyenfull_scraper_raises_when_no_chapters(tmp_path):
    with patch("scrapers.truyenfull.polite_get", return_value=_resp("<html></html>")), \
         patch("scrapers.truyenfull.make_session", return_value=MagicMock()):
        with pytest.raises(RuntimeError, match="No chapters found"):
            TruyenfullScraper().scrape("https://truyenfull.vision/test-book/", tmp_path)


# ---------------------------------------------------------------------------
# ZingtruyenScraper.scrape — integration (mocked HTTP)
# ---------------------------------------------------------------------------

def test_zingtruyen_scraper_downloads_all_chapters(tmp_path):
    listing = (FIXTURES / "zingtruyen_listing.html").read_text(encoding="utf-8")
    group = (FIXTURES / "zingtruyen_group.html").read_text(encoding="utf-8")

    def fake_get(session, url, **kw):
        return _resp(group if "chuong-1-50" in url else listing)

    with patch("scrapers.zingtruyen.polite_get", side_effect=fake_get), \
         patch("scrapers.zingtruyen.make_session", return_value=MagicMock()):
        count = ZingtruyenScraper().scrape(
            "https://zingtruyen.store/story/test-book/1.html", tmp_path
        )

    assert count == 2
    assert (tmp_path / "ch_001.md").exists()
    assert (tmp_path / "ch_002.md").exists()


def test_zingtruyen_scraper_raises_when_no_groups(tmp_path):
    with patch("scrapers.zingtruyen.polite_get", return_value=_resp("<html></html>")), \
         patch("scrapers.zingtruyen.make_session", return_value=MagicMock()):
        with pytest.raises(RuntimeError, match="No chapter groups"):
            ZingtruyenScraper().scrape(
                "https://zingtruyen.store/story/test-book/1.html", tmp_path
            )
