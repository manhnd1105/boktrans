"""Scraper for truyenfull.vision — paginated chapter listing."""
import re
from collections.abc import Callable
from pathlib import Path

from .base import html_clean, make_session, polite_get, write_chapter


def _parse_chapter_list(html: str, book_slug: str) -> list[dict]:
    pattern = (
        rf'href="(https://truyenfull\.vision/{re.escape(book_slug)}/chuong-\d+/)"'
        r'[^>]*title="[^-]+-\s*([^"]+)"'
    )
    return [{"url": url, "title": title.strip()} for url, title in re.findall(pattern, html)]


def _parse_chapter_content(html: str) -> tuple[str, str]:
    title_match = re.search(r'class="chapter-title"[^>]*title="[^-]+-\s*([^"]+)"', html)
    if title_match:
        title = title_match.group(1).strip()
    else:
        h2 = re.search(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL)
        title = html_clean(h2.group(1)) if h2 else "Không rõ tiêu đề"

    start = re.search(r'<div[^>]*class="[^"]*chapter-c[^"]*"[^>]*>', html)
    if not start:
        return title, ""
    content = html[start.end():]
    nav = content.find('class="chapter-nav"')
    if nav > 0:
        content = content[:nav]

    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
    body = "\n\n".join(html_clean(p) for p in paragraphs if p.strip())
    return title, body


class TruyenfullScraper:
    def scrape(
        self,
        book_url: str,
        dest_dir: Path,
        progress_cb: Callable[[str], None] = print,
    ) -> int:
        """Scrape all chapters from a truyenfull.vision book URL. Returns chapter count."""
        slug_match = re.search(r'truyenfull\.vision/([^/?#]+)', book_url)
        if not slug_match:
            raise ValueError(f"Cannot parse book slug from URL: {book_url}")
        slug = slug_match.group(1)
        base = f"https://truyenfull.vision/{slug}"

        session = make_session()
        all_chapters: list[dict] = []
        page = 1
        while True:
            url = f"{base}/trang-{page}/"
            resp = polite_get(session, url)
            found = _parse_chapter_list(resp.text, slug)
            if not found:
                break
            all_chapters.extend(found)
            page += 1

        if not all_chapters:
            raise RuntimeError(f"No chapters found at {book_url}. Site HTML may have changed.")

        progress_cb(f"Found {len(all_chapters)} chapters. Downloading...")
        for i, ch in enumerate(all_chapters, start=1):
            out = dest_dir / f"ch_{i:03d}.md"
            if out.exists():
                continue
            resp = polite_get(session, ch["url"])
            title, body = _parse_chapter_content(resp.text)
            write_chapter(i, title, body, dest_dir)
            if i % 50 == 0 or i == len(all_chapters):
                progress_cb(f"Scraped {i} / {len(all_chapters)} chapters...")

        return len(all_chapters)
