"""Orchestrates: scrape → translate → combine → epub for a single job."""
import os
import shutil
import subprocess
import uuid
from collections.abc import Callable
from pathlib import Path

from scrapers import detect_scraper
from translator import translate_all

JOBS_DIR = Path(os.environ.get("JOBS_DIR", str(Path(__file__).parent / "jobs")))


def _combine(output_dir: Path, book_md: Path) -> None:
    chapters = sorted(output_dir.glob("ch_*.md"))
    if not chapters:
        raise RuntimeError("No translated chapters to combine.")
    parts = [p.read_text(encoding="utf-8").strip() for p in chapters]
    book_md.write_text("\n\n---\n\n".join(parts) + "\n", encoding="utf-8")


def _to_epub(book_md: Path, book_epub: Path, title: str) -> None:
    result = subprocess.run(
        [
            "pandoc", str(book_md),
            "-o", str(book_epub),
            "--metadata", f"title={title}",
            "--metadata", "lang=vi",
            "--toc",
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"pandoc failed: {result.stderr}")


def run_job(
    book_url: str,
    progress_cb: Callable[[str], None] = print,
    chapter_filter: set[int] | None = None,
) -> Path:
    """Run the full pipeline for book_url. Returns path to the generated epub."""
    job_id = uuid.uuid4().hex[:8]
    job_dir = JOBS_DIR / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)

    try:
        progress_cb(f"Scraping {book_url}...")
        scraper = detect_scraper(book_url)
        scraper.scrape(book_url, input_dir, progress_cb, chapter_filter)

        progress_cb("Translating chapters...")
        translate_all(input_dir, output_dir, progress_cb, chapter_filter)

        progress_cb("Combining chapters...")
        book_md = job_dir / "book.md"
        _combine(output_dir, book_md)

        # progress_cb("Generating EPUB...")
        # book_epub = job_dir / "book.epub"
        # title = book_url.rstrip("/").split("/")[-1].replace("-", " ").title()
        # _to_epub(book_md, book_epub, title)

        progress_cb("Done.")
        return book_md

    except Exception:
        shutil.rmtree(job_dir, ignore_errors=True)
        raise


def cleanup_job(epub_path: Path) -> None:
    shutil.rmtree(epub_path.parent, ignore_errors=True)
