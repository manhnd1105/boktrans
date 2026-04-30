"""Scraper for truyenfull.vision — paginated chapter listing."""
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .base import html_clean, make_session, polite_get, write_chapter

_WORKERS = 5


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


def _fetch_chapter(
    idx: int,
    ch: dict,
    dest_dir: Path,
    total: int,
    progress_cb: Callable[[str], None],
) -> None:
    out = dest_dir / f"ch_{idx:03d}.md"
    if out.exists():
        progress_cb(f"  [{idx}/{total}] already saved, skipping")
        return
    session = make_session()
    progress_cb(f"  [{idx}/{total}] Scraping: {ch['title']}")
    try:
        resp = polite_get(session, ch["url"])
        title, body = _parse_chapter_content(resp.text)
        write_chapter(idx, title, body, dest_dir)
        progress_cb(f"  [{idx}/{total}] Saved: {title} ({len(body)} chars)")
    except Exception as e:
        progress_cb(f"  [{idx}/{total}] FAILED: {ch['title']} — {e}")


class TruyenfullScraper:
    def get_book_info(self, book_url: str) -> dict:
        """Return {"slug": ..., "author": ..., "dir_name": ...} from the book listing page."""
        slug_match = re.search(r'truyenfull\.vision/([^/?#]+)', book_url)
        slug = slug_match.group(1).strip("/") if slug_match else "unknown"
        try:
            session = make_session()
            resp = polite_get(session, book_url)
            author_match = re.search(r'truyenfull\.vision/tac-gia/([^/"]+)/', resp.text)
            author = author_match.group(1).strip("/") if author_match else None
        except Exception:
            author = None
        dir_name = f"{slug}-{author}" if author else slug
        return {"slug": slug, "author": author, "dir_name": dir_name}

    def scrape(
        self,
        book_url: str,
        dest_dir: Path,
        progress_cb: Callable[[str], None] = print,
        chapter_filter: set[int] | None = None,
    ) -> int:
        """Scrape chapters from a truyenfull.vision book URL. Returns chapter count."""
        slug_match = re.search(r'truyenfull\.vision/([^/?#]+)', book_url)
        if not slug_match:
            raise ValueError(f"Cannot parse book slug from URL: {book_url}")
        slug = slug_match.group(1)
        base = f"https://truyenfull.vision/{slug}"

        dest_dir.mkdir(parents=True, exist_ok=True)
        cache_file = dest_dir / "_chapters.json"

        if cache_file.exists():
            all_chapters: list[dict] = json.loads(cache_file.read_text(encoding="utf-8"))
            progress_cb(f"Loaded {len(all_chapters)} chapters from cache.")
        else:
            session = make_session()
            all_chapters = []
            page = 1
            max_needed = max(chapter_filter) if chapter_filter else None
            progress_cb("Finding chapters...")
            while True:
                progress_cb(f"  Checking listing page {page}...")
                url = f"{base}/trang-{page}/"
                resp = polite_get(session, url)
                found = _parse_chapter_list(resp.text, slug)
                if not found:
                    break
                all_chapters.extend(found)
                if max_needed is not None and len(all_chapters) >= max_needed:
                    break
                page += 1

            if not all_chapters:
                raise RuntimeError(f"No chapters found at {book_url}. Site HTML may have changed.")

            cache_file.write_text(
                json.dumps(all_chapters, ensure_ascii=False), encoding="utf-8"
            )
            progress_cb(f"Found {len(all_chapters)} chapters, cached to {cache_file.name}.")

        if chapter_filter is not None:
            selected = [(i, all_chapters[i - 1]) for i in sorted(chapter_filter) if i <= len(all_chapters)]
        else:
            selected = list(enumerate(all_chapters, start=1))

        total = len(all_chapters)
        progress_cb(f"Downloading {len(selected)} chapters with {_WORKERS} parallel workers...")
        with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_chapter, i, ch, dest_dir, total, progress_cb): i
                for i, ch in selected
            }
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    progress_cb(f"  Unexpected worker error: {e}")

        return len(selected)
