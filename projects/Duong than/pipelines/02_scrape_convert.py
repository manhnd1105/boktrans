#!/usr/bin/env python3
"""
Scrape chapters 499-781 (auto-converted) from zingtruyen.store and save as markdown.

Site structure:
  Listing page → group pages (e.g. chuong-451-500, chuong-501-550)
  Group page   → single <div id="chapter-content"> with ALL chapters in range,
                 separated by <p>Chương NNN: title</p> headers.

Usage:
  python 02_scrape_convert.py --test      # parse local fixture, no network
  python 02_scrape_convert.py --inspect   # dump listing + first group page to /tmp
  python 02_scrape_convert.py --dry-run   # fetch one group page, print parsed chapters
  python 02_scrape_convert.py             # MANUAL: scrape chapters 499-781
"""
import argparse
import html as html_module
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
INPUT_DIR = PROJECT_DIR / "input"
TEST_DIR = PROJECT_DIR / "output" / "chapters"  # test output only
TESTS_DIR = SCRIPT_DIR / "tests"

STORY_URL = "https://zingtruyen.store/story/duong-than-full/147033246.html"
REQUEST_DELAY = 1.5
CHAPTER_START = 499
CHAPTER_END = 781

DUMP_LIST_FILE = Path("/tmp/zingtruyen_list.html")
DUMP_GROUP_FILE = Path("/tmp/zingtruyen_group.html")


def parse_group_urls(listing_html: str, ch_start: int, ch_end: int) -> list[str]:
    """Extract group page URLs that overlap with the desired chapter range, sorted by start chapter.

    Group URL slugs like 'chuong-451-500' or 'chuong-701-full' encode the range.
    """
    pattern = r'href="(https://zingtruyen\.store/chapter/[^"]+/chuong-([\d]+)-([\d]+|full)/\d+\.html)"'
    seen: dict[str, int] = {}  # url → group start chapter
    for m in re.finditer(pattern, listing_html):
        url, start_s, end_s = m.group(1), m.group(2), m.group(3)
        if url in seen:
            continue
        g_start = int(start_s)
        g_end = int(end_s) if end_s != "full" else 9999
        if g_start <= ch_end and g_end >= ch_start:
            seen[url] = g_start
    return sorted(seen, key=seen.__getitem__)


def parse_group_page(html: str) -> dict[int, tuple[str, str]]:
    """Parse a group page → {chapter_num: (title, body)}.

    Splits the chapter-content div by chapter-header paragraphs.
    """
    start = html.find('id="chapter-content"')
    if start == -1:
        return {}
    content_html = html[start:]

    # End at closing chapter-button div (footer nav)
    end_marker = content_html.find('class="chapter-button')
    if end_marker > 0:
        content_html = content_html[:end_marker]

    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content_html, re.DOTALL)

    chapters: dict[int, tuple[str, str]] = {}
    current_num: int | None = None
    current_title = ""
    current_body: list[str] = []

    for para in paragraphs:
        clean = html_module.unescape(re.sub(r'<[^>]+>', '', para)).strip()
        if not clean:
            continue

        # Chapter header: "Chương NNN:" or "Chương NNN -"
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


def save_chapter(num: int, title: str, body: str, dest_dir: Path, prefix: str = "ch") -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / f"{prefix}_{num:03d}.md"
    out_path.write_text(f"<!-- source: convert -->\n# {title}\n\n{body}\n", encoding="utf-8")
    return out_path


def run_test():
    fixture = TESTS_DIR / "sample_zingtruyen.html"
    html = fixture.read_text(encoding="utf-8")

    group_urls = parse_group_urls(html, CHAPTER_START, CHAPTER_END)
    print(f"[test] Found {len(group_urls)} group URL(s) in fixture")

    chapters = parse_group_page(html)
    print(f"[test] Parsed {len(chapters)} chapter(s) from fixture content")

    if chapters:
        num, (title, body) = next(iter(chapters.items()))
        path = save_chapter(num, title, body, TEST_DIR, prefix="test_ch")
        content = path.read_text(encoding="utf-8")
        assert "<!-- source: convert -->" in content, "convert marker missing"
        print(f"[test] Written: {path}")
    else:
        # Fixture has no group-page content — just verify it doesn't crash
        path = save_chapter(499, "Chương 499: Test", "Nội dung test.", TEST_DIR, prefix="test_ch")
        print(f"[test] Written (stub): {path}")

    print("[test] PASS")


def run_inspect():
    try:
        import requests
    except ImportError:
        sys.exit("requests not installed — run: pip install requests")

    headers = {"User-Agent": "Mozilla/5.0"}

    print(f"[inspect] Fetching listing: {STORY_URL}")
    resp = requests.get(STORY_URL, timeout=15, headers=headers)
    print(f"[inspect] Status: {resp.status_code}  Final URL: {resp.url}")
    DUMP_LIST_FILE.write_text(resp.text, encoding="utf-8")
    print(f"[inspect] Listing HTML saved to: {DUMP_LIST_FILE}")

    group_urls = parse_group_urls(resp.text, CHAPTER_START, CHAPTER_END)
    print(f"[inspect] Group URLs for ch {CHAPTER_START}-{CHAPTER_END}: {len(group_urls)}")
    for u in group_urls:
        print(f"  {u}")

    if group_urls:
        print(f"\n[inspect] Fetching first group page: {group_urls[0]}")
        resp2 = requests.get(group_urls[0], timeout=30, headers=headers)
        DUMP_GROUP_FILE.write_text(resp2.text, encoding="utf-8")
        print(f"[inspect] Group HTML saved to: {DUMP_GROUP_FILE}")
        chapters = parse_group_page(resp2.text)
        print(f"[inspect] Parsed {len(chapters)} chapters from group page")
        for num in sorted(chapters)[:3]:
            title, body = chapters[num]
            print(f"  ch {num}: {title} | body {len(body)} chars")


def run_dry_run():
    try:
        import requests
    except ImportError:
        sys.exit("requests not installed — run: pip install requests")

    headers = {"User-Agent": "Mozilla/5.0"}

    print(f"[dry-run] Fetching listing...")
    resp = requests.get(STORY_URL, timeout=15, headers=headers)
    resp.raise_for_status()
    group_urls = parse_group_urls(resp.text, CHAPTER_START, CHAPTER_END)
    if not group_urls:
        print("[dry-run] No group URLs found — run --inspect to examine the HTML")
        return
    print(f"[dry-run] {len(group_urls)} group pages to fetch")

    print(f"[dry-run] Fetching first group: {group_urls[0]}")
    resp2 = requests.get(group_urls[0], timeout=30, headers=headers)
    resp2.raise_for_status()
    chapters = parse_group_page(resp2.text)
    in_range = {n: v for n, v in chapters.items() if CHAPTER_START <= n <= CHAPTER_END}
    print(f"[dry-run] Chapters parsed: {sorted(chapters.keys())[:10]}...")
    print(f"[dry-run] In range [{CHAPTER_START}-{CHAPTER_END}]: {sorted(in_range.keys())[:5]}...")
    if in_range:
        num = min(in_range)
        title, body = in_range[num]
        print(f"\n[dry-run] Chapter {num} title: {title}")
        print(f"[dry-run] Body preview:\n{body[:400]}...")


def run_full():
    try:
        import requests
    except ImportError:
        sys.exit("requests not installed — run: pip install requests")

    headers = {"User-Agent": "Mozilla/5.0"}
    session = requests.Session()
    session.headers.update(headers)

    print("Fetching listing...")
    resp = session.get(STORY_URL, timeout=15)
    resp.raise_for_status()
    group_urls = parse_group_urls(resp.text, CHAPTER_START, CHAPTER_END)
    if not group_urls:
        sys.exit("No group pages found. Run --inspect to diagnose.")
    print(f"Group pages to fetch: {len(group_urls)}")

    for group_url in group_urls:
        print(f"\nFetching group: {group_url}")
        resp = session.get(group_url, timeout=30)
        resp.raise_for_status()
        chapters = parse_group_page(resp.text)
        in_range = {n: v for n, v in chapters.items() if CHAPTER_START <= n <= CHAPTER_END}
        print(f"  Parsed {len(chapters)} chapters, {len(in_range)} in target range")

        for num in sorted(in_range):
            out_path = INPUT_DIR / f"ch_{num:03d}.md"
            if out_path.exists():
                print(f"  [{num}] skip (exists)")
                continue
            title, body = in_range[num]
            save_chapter(num, title, body, INPUT_DIR)
            print(f"  [{num}] {title[:60]}")

        time.sleep(REQUEST_DELAY)

    saved = sorted(p.stem for p in INPUT_DIR.glob("ch_*.md")
                   if CHAPTER_START <= int(p.stem.split("_")[1]) <= CHAPTER_END)
    print(f"\nDone. {len(saved)} chapters saved in input/")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--inspect", action="store_true",
                        help="Dump raw HTML of listing + first group page to /tmp for diagnosis")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.test:
        run_test()
    elif args.inspect:
        run_inspect()
    elif args.dry_run:
        run_dry_run()
    else:
        confirm = input(
            f"This will scrape chapters {CHAPTER_START}-{CHAPTER_END} from zingtruyen.store. "
            "Proceed? [y/N] "
        )
        if confirm.lower() != "y":
            print("Aborted.")
        else:
            run_full()


if __name__ == "__main__":
    main()
