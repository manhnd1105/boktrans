"""Scraper for zingtruyen.store — group-page chapter listing."""
import re
from collections.abc import Callable
from pathlib import Path

from .base import html_clean, make_session, polite_get, write_chapter


def _parse_group_urls(listing_html: str) -> list[str]:
    pattern = r'href="(https://zingtruyen\.store/chapter/[^"]+/chuong-([\d]+)-([\d]+|full)/\d+\.html)"'
    seen: dict[str, int] = {}
    for m in re.finditer(pattern, listing_html):
        url, start_s = m.group(1), m.group(2)
        if url not in seen:
            seen[url] = int(start_s)
    return sorted(seen, key=seen.__getitem__)


def _parse_group_page(html: str) -> dict[int, tuple[str, str]]:
    start = html.find('id="chapter-content"')
    if start == -1:
        return {}
    content = html[start:]
    end = content.find('class="chapter-button')
    if end > 0:
        content = content[:end]

    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content, re.DOTALL)
    chapters: dict[int, tuple[str, str]] = {}
    current_num: int | None = None
    current_title = ""
    current_body: list[str] = []

    for para in paragraphs:
        clean = html_clean(para)
        if not clean:
            continue
        ch_match = re.match(r'^\s*Chương\s+(\d+)\s*[:\-]\s*(.*)', clean, re.IGNORECASE)
        if ch_match:
            if current_num is not None:
                chapters[current_num] = (current_title, "\n\n".join(current_body))
            current_num = int(ch_match.group(1))
            current_title = f"Chương {current_num}: {ch_match.group(2).strip()}"
            current_body = []
        elif current_num is not None:
            current_body.append(clean)

    if current_num is not None:
        chapters[current_num] = (current_title, "\n\n".join(current_body))
    return chapters


class ZingtruyenScraper:
    def scrape(
        self,
        book_url: str,
        dest_dir: Path,
        progress_cb: Callable[[str], None] = print,
    ) -> int:
        """Scrape all chapters from a zingtruyen.store story URL. Returns chapter count."""
        session = make_session()
        resp = polite_get(session, book_url)
        group_urls = _parse_group_urls(resp.text)
        if not group_urls:
            raise RuntimeError(f"No chapter groups found at {book_url}. Site HTML may have changed.")

        progress_cb(f"Found {len(group_urls)} chapter groups. Downloading...")
        saved = 0
        for group_url in group_urls:
            resp = polite_get(session, group_url, timeout=30)
            chapters = _parse_group_page(resp.text)
            for num in sorted(chapters):
                out = dest_dir / f"ch_{num:03d}.md"
                if out.exists():
                    continue
                title, body = chapters[num]
                write_chapter(num, title, body, dest_dir)
                saved += 1
            if chapters:
                progress_cb(f"Scraped group ending ch {max(chapters)}...")

        return saved
