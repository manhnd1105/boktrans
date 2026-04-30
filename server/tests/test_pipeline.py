"""Integration tests for pipeline.py (scraper, translator, pandoc mocked)."""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pipeline


# ---------------------------------------------------------------------------
# _combine
# ---------------------------------------------------------------------------

def test_combine_merges_chapters(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    (out / "ch_001.md").write_text("# Ch 1\n\nBody one.", encoding="utf-8")
    (out / "ch_002.md").write_text("# Ch 2\n\nBody two.", encoding="utf-8")
    book_md = tmp_path / "book.md"
    pipeline._combine(out, book_md)
    content = book_md.read_text(encoding="utf-8")
    assert "Body one." in content
    assert "Body two." in content
    assert "---" in content


def test_combine_preserves_chapter_order(tmp_path):
    out = tmp_path / "output"
    out.mkdir()
    (out / "ch_002.md").write_text("Ch2", encoding="utf-8")
    (out / "ch_001.md").write_text("Ch1", encoding="utf-8")
    book_md = tmp_path / "book.md"
    pipeline._combine(out, book_md)
    content = book_md.read_text(encoding="utf-8")
    assert content.index("Ch1") < content.index("Ch2")


def test_combine_raises_on_empty_output_dir(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RuntimeError, match="No translated chapters"):
        pipeline._combine(empty, tmp_path / "book.md")


# ---------------------------------------------------------------------------
# cleanup_job
# ---------------------------------------------------------------------------

def test_cleanup_job_removes_directory(tmp_path):
    job_dir = tmp_path / "abc123"
    job_dir.mkdir()
    epub = job_dir / "book.epub"
    epub.write_bytes(b"fake")
    pipeline.cleanup_job(epub)
    assert not job_dir.exists()


def test_cleanup_job_tolerates_missing_dir(tmp_path):
    pipeline.cleanup_job(tmp_path / "nonexistent" / "book.epub")  # must not raise


# ---------------------------------------------------------------------------
# Helpers shared by run_job tests
# ---------------------------------------------------------------------------

def _make_fake_scraper():
    def fake_scrape(book_url, dest_dir, progress_cb=print):
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "ch_001.md").write_text("# Ch 1\n\nNội dung một.\n", encoding="utf-8")
        (dest_dir / "ch_002.md").write_text("# Ch 2\n\nNội dung hai.\n", encoding="utf-8")
        return 2
    m = MagicMock()
    m.scrape = fake_scrape
    return m


def _fake_translate(input_dir, output_dir, progress_cb=print):
    output_dir.mkdir(parents=True, exist_ok=True)
    for f in sorted(input_dir.glob("ch_*.md")):
        (output_dir / f.name).write_text(
            f.read_text(encoding="utf-8") + "\n[dịch]\n", encoding="utf-8"
        )
    return len(list(input_dir.glob("ch_*.md")))


def _fake_pandoc_ok(cmd, **kwargs):
    r = MagicMock()
    r.returncode = 0
    r.stderr = ""
    Path(cmd[cmd.index("-o") + 1]).write_bytes(b"FAKE_EPUB")
    return r


# ---------------------------------------------------------------------------
# run_job
# ---------------------------------------------------------------------------

def test_run_job_returns_epub_path(tmp_path):
    with patch("pipeline.JOBS_DIR", tmp_path), \
         patch("pipeline.detect_scraper", return_value=_make_fake_scraper()), \
         patch("pipeline.translate_all", side_effect=_fake_translate), \
         patch("pipeline.subprocess.run", side_effect=_fake_pandoc_ok):
        epub = pipeline.run_job("https://truyenfull.vision/test-book/")

    assert epub.exists()
    assert epub.suffix == ".epub"


def test_run_job_cleans_up_job_dir_on_failure(tmp_path):
    with patch("pipeline.JOBS_DIR", tmp_path), \
         patch("pipeline.detect_scraper", side_effect=ValueError("Unsupported site")):
        with pytest.raises(ValueError):
            pipeline.run_job("https://unknown-site.com/book")

    assert list(tmp_path.iterdir()) == []


def test_run_job_calls_progress_cb(tmp_path):
    messages = []
    with patch("pipeline.JOBS_DIR", tmp_path), \
         patch("pipeline.detect_scraper", return_value=_make_fake_scraper()), \
         patch("pipeline.translate_all", side_effect=_fake_translate), \
         patch("pipeline.subprocess.run", side_effect=_fake_pandoc_ok):
        pipeline.run_job(
            "https://truyenfull.vision/test-book/", progress_cb=messages.append
        )

    assert any("Scraping" in m for m in messages)
    assert any("Translating" in m for m in messages)
    assert any("EPUB" in m for m in messages)


def test_run_job_raises_when_pandoc_fails(tmp_path):
    def failing_pandoc(cmd, **kwargs):
        r = MagicMock()
        r.returncode = 1
        r.stderr = "pandoc: command not found"
        return r

    with patch("pipeline.JOBS_DIR", tmp_path), \
         patch("pipeline.detect_scraper", return_value=_make_fake_scraper()), \
         patch("pipeline.translate_all", side_effect=_fake_translate), \
         patch("pipeline.subprocess.run", side_effect=failing_pandoc):
        with pytest.raises(RuntimeError, match="pandoc failed"):
            pipeline.run_job("https://truyenfull.vision/test-book/")
