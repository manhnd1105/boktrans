"""System tests: full pipeline from fixture HTML to epub.

HTTP and LLM are mocked; all other pipeline logic (parsers, combine, path
handling) runs for real against the fixture HTML files.
"""
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pipeline as pipeline

FIXTURES = Path(__file__).parent / "fixtures"

TRANSLATED_CHAPTER = (
    "# Chương {n}: Tiêu đề đã dịch\n\n"
    "Đây là bản dịch tiếng Việt đầy đủ và tự nhiên cho chương {n}, "
    "đảm bảo vượt qua ngưỡng kiểm tra chất lượng tối thiểu năm mươi phần trăm."
)


def _resp(text: str) -> MagicMock:
    r = MagicMock()
    r.text = text
    r.raise_for_status = MagicMock()
    return r


def _fake_pandoc(cmd, **kwargs):
    r = MagicMock()
    r.returncode = 0
    r.stderr = ""
    Path(cmd[cmd.index("-o") + 1]).write_bytes(b"FAKE_EPUB_BYTES")
    return r


def _fake_llm(prompt: str) -> str:
    m = re.search(r'Chương (\d+)', prompt)
    n = m.group(1) if m else "1"
    return TRANSLATED_CHAPTER.format(n=n)


# ---------------------------------------------------------------------------
# System test: truyenfull → epub
# ---------------------------------------------------------------------------

def test_system_truyenfull_produces_epub(tmp_path):
    listing = (FIXTURES / "truyenfull_listing.html").read_text(encoding="utf-8")
    chapter = (FIXTURES / "truyenfull_chapter.html").read_text(encoding="utf-8")

    def fake_http(session, url, **kw):
        if "trang-1" in url:
            return _resp(listing)
        if "trang-" in url:
            return _resp("<html></html>")
        return _resp(chapter)

    with patch("pipeline.JOBS_DIR", tmp_path), \
         patch("scrapers.truyenfull.polite_get", side_effect=fake_http), \
         patch("scrapers.truyenfull.make_session", return_value=MagicMock()), \
         patch("translator._call_with_fallback", side_effect=_fake_llm), \
         patch("pipeline.subprocess.run", side_effect=_fake_pandoc):
        epub = pipeline.run_job("https://truyenfull.vision/test-book/")

    assert epub.exists()
    assert epub.suffix == ".epub"


def test_system_truyenfull_book_md_contains_translated_content(tmp_path):
    listing = (FIXTURES / "truyenfull_listing.html").read_text(encoding="utf-8")
    chapter = (FIXTURES / "truyenfull_chapter.html").read_text(encoding="utf-8")

    def fake_http(session, url, **kw):
        if "trang-1" in url:
            return _resp(listing)
        if "trang-" in url:
            return _resp("<html></html>")
        return _resp(chapter)

    with patch("pipeline.JOBS_DIR", tmp_path), \
         patch("scrapers.truyenfull.polite_get", side_effect=fake_http), \
         patch("scrapers.truyenfull.make_session", return_value=MagicMock()), \
         patch("translator._call_with_fallback", side_effect=_fake_llm), \
         patch("pipeline.subprocess.run", side_effect=_fake_pandoc):
        epub = pipeline.run_job("https://truyenfull.vision/test-book/")

    book_md = (epub.parent / "book.md").read_text(encoding="utf-8")
    assert "bản dịch tiếng Việt" in book_md
    assert "---" in book_md  # chapter separator present


def test_system_truyenfull_two_chapters_in_output(tmp_path):
    listing = (FIXTURES / "truyenfull_listing.html").read_text(encoding="utf-8")
    chapter = (FIXTURES / "truyenfull_chapter.html").read_text(encoding="utf-8")

    def fake_http(session, url, **kw):
        if "trang-1" in url:
            return _resp(listing)
        if "trang-" in url:
            return _resp("<html></html>")
        return _resp(chapter)

    with patch("pipeline.JOBS_DIR", tmp_path), \
         patch("scrapers.truyenfull.polite_get", side_effect=fake_http), \
         patch("scrapers.truyenfull.make_session", return_value=MagicMock()), \
         patch("translator._call_with_fallback", side_effect=_fake_llm), \
         patch("pipeline.subprocess.run", side_effect=_fake_pandoc):
        epub = pipeline.run_job("https://truyenfull.vision/test-book/")

    output_dir = epub.parent / "output"
    translated = list(output_dir.glob("ch_*.md"))
    assert len(translated) == 2


# ---------------------------------------------------------------------------
# System test: zingtruyen → epub
# ---------------------------------------------------------------------------

def test_system_zingtruyen_produces_epub(tmp_path):
    listing = (FIXTURES / "zingtruyen_listing.html").read_text(encoding="utf-8")
    group = (FIXTURES / "zingtruyen_group.html").read_text(encoding="utf-8")

    def fake_http(session, url, **kw):
        return _resp(group if "chuong-1-50" in url else listing)

    with patch("pipeline.JOBS_DIR", tmp_path), \
         patch("scrapers.zingtruyen.polite_get", side_effect=fake_http), \
         patch("scrapers.zingtruyen.make_session", return_value=MagicMock()), \
         patch("translator._call_with_fallback", side_effect=_fake_llm), \
         patch("pipeline.subprocess.run", side_effect=_fake_pandoc):
        epub = pipeline.run_job("https://zingtruyen.store/story/test-book/1.html")

    assert epub.exists()
    assert epub.suffix == ".epub"


# ---------------------------------------------------------------------------
# System test: unsupported URL
# ---------------------------------------------------------------------------

def test_system_unsupported_url_raises_and_cleans_up(tmp_path):
    with patch("pipeline.JOBS_DIR", tmp_path):
        with pytest.raises(ValueError, match="Unsupported"):
            pipeline.run_job("https://unknown-site.com/some-book/")

    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# System test: partial translation failure — pipeline still produces epub
# ---------------------------------------------------------------------------

def test_system_partial_translation_failure_still_produces_epub(tmp_path):
    listing = (FIXTURES / "truyenfull_listing.html").read_text(encoding="utf-8")
    chapter = (FIXTURES / "truyenfull_chapter.html").read_text(encoding="utf-8")

    def fake_http(session, url, **kw):
        if "trang-1" in url:
            return _resp(listing)
        if "trang-" in url:
            return _resp("<html></html>")
        return _resp(chapter)

    call_count = [0]
    def flaky_llm(prompt):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Transient model error")
        return _fake_llm(prompt)

    with patch("pipeline.JOBS_DIR", tmp_path), \
         patch("scrapers.truyenfull.polite_get", side_effect=fake_http), \
         patch("scrapers.truyenfull.make_session", return_value=MagicMock()), \
         patch("translator._call_with_fallback", side_effect=flaky_llm), \
         patch("pipeline.subprocess.run", side_effect=_fake_pandoc):
        epub = pipeline.run_job("https://truyenfull.vision/test-book/")

    assert epub.exists()
