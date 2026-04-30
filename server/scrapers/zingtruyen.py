"""Scraper for zingtruyen.store — group-page chapter listing."""
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .base import html_clean, make_session, polite_get, write_chapter

_WORKERS = 5


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


def _fetch_group(
    g_idx: int,
    group_url: str,
    total_groups: int,
    progress_cb: Callable[[str], None],
) -> dict[int, tuple[str, str]]:
    progress_cb(f"  [group {g_idx}/{total_groups}] Fetching...")
    session = make_session()
    try:
        resp = polite_get(session, group_url, timeout=30)
        chapters = _parse_group_page(resp.text)
        if chapters:
            progress_cb(
                f"  [group {g_idx}/{total_groups}] Parsed chapters {min(chapters)}–{max(chapters)}"
            )
        return chapters
    except Exception as e:
        progress_cb(f"  [group {g_idx}/{total_groups}] FAILED — {e}")
        return {}


def _group_range(url: str) -> tuple[int, int] | None:
    """Extract (start, end) chapter numbers from a group URL, or None if unparseable."""
    m = re.search(r'/chuong-(\d+)-(?:(\d+)|full)/', url)
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else start
    return start, end


class ZingtruyenScraper:
    def scrape(
        self,
        book_url: str,
        dest_dir: Path,
        progress_cb: Callable[[str], None] = print,
        chapter_filter: set[int] | None = None,
    ) -> int:
        """Scrape chapters from a zingtruyen.store story URL. Returns chapter count."""
        dest_dir.mkdir(parents=True, exist_ok=True)
        cache_file = dest_dir / "_groups.json"

        session = make_session()
        resp = polite_get(session, book_url)
        progress_cb("Parsing chapter groups...")
        group_urls = _parse_group_urls(resp.text)
        if not group_urls:
            raise RuntimeError(f"No chapter groups found at {book_url}. Site HTML may have changed.")

        if chapter_filter is not None:
            def _overlaps(url: str) -> bool:
                r = _group_range(url)
                return r is None or any(r[0] <= n <= r[1] for n in chapter_filter)
            group_urls = [u for u in group_urls if _overlaps(u)]
            progress_cb(f"  {len(group_urls)} group(s) overlap with chapter filter.")

        total_groups = len(group_urls)

        # Load cached group→chapter mapping to skip already-complete groups on resume
        group_chapters: dict[str, list[int]] = {}
        if cache_file.exists():
            try:
                group_chapters = json.loads(cache_file.read_text(encoding="utf-8")).get(
                    "group_chapters", {}
                )
            except Exception:
                group_chapters = {}

        def _needs_fetch(url: str) -> bool:
            known = group_chapters.get(url)
            if not known:
                return True
            needed = [n for n in known if chapter_filter is None or n in chapter_filter]
            return any(not (dest_dir / f"ch_{n:03d}.md").exists() for n in needed)

        groups_to_fetch = [
            (g_idx, url) for g_idx, url in enumerate(group_urls, start=1) if _needs_fetch(url)
        ]
        skipped = total_groups - len(groups_to_fetch)
        if skipped:
            progress_cb(f"  {skipped}/{total_groups} groups already complete, skipping.")
        progress_cb(
            f"Fetching {len(groups_to_fetch)} group pages with {_WORKERS} parallel workers..."
        )

        saved = 0
        with ThreadPoolExecutor(max_workers=_WORKERS) as executor:
            futures = {
                executor.submit(_fetch_group, g_idx, url, total_groups, progress_cb): url
                for g_idx, url in groups_to_fetch
            }
            for future in as_completed(futures):
                url = futures[future]
                try:
                    chapters = future.result()
                    group_chapters[url] = list(chapters.keys())
                    for num in sorted(chapters):
                        if chapter_filter is not None and num not in chapter_filter:
                            continue
                        out = dest_dir / f"ch_{num:03d}.md"
                        if out.exists():
                            progress_cb(f"    ch_{num:03d} already saved, skipping")
                            continue
                        title, body = chapters[num]
                        write_chapter(num, title, body, dest_dir)
                        saved += 1
                        progress_cb(f"    ch_{num:03d} saved: {title} ({len(body)} chars)")
                except Exception as e:
                    progress_cb(f"  Unexpected worker error for {url}: {e}")

        cache_file.write_text(
            json.dumps({"group_chapters": group_chapters}, ensure_ascii=False), encoding="utf-8"
        )
        progress_cb(f"Done. Saved {saved} new chapters.")
        return saved
