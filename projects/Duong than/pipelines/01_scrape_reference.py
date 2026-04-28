#!/usr/bin/env python3
"""
Scrape chapters 1-CHAPTER_LIMIT from truyenfull.vision and save as markdown.

Usage:
  python 01_scrape_reference.py --test      # parse local fixture, no network
  python 01_scrape_reference.py --dry-run   # fetch and parse one chapter, print only
  python 01_scrape_reference.py             # MANUAL: scrape all CHAPTER_LIMIT chapters
"""
import argparse
import re
import sys
import time
from pathlib import Path

DUMP_FILE = Path("/tmp/truyenfull_page1.html")

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
INPUT_DIR = PROJECT_DIR / "input"
TEST_DIR = PROJECT_DIR / "output" / "chapters"  # test output only
TESTS_DIR = SCRIPT_DIR / "tests"

BASE_URL = "https://truyenfull.vision/duong-than"
REQUEST_DELAY = 1.0  # seconds between requests to be polite
CHAPTER_LIMIT = 498  # total chapters to scrape


def parse_chapter_list(html: str) -> list[dict]:
    """Extract chapter links from a listing page.

    The site uses full absolute URLs and puts the title in the 'title' attribute:
      href="https://truyenfull.vision/duong-than/chuong-N/" title="Dương Thần - Chương N: TITLE"
    """
    pattern = r'href="(https://truyenfull\.vision/duong-than/chuong-\d+/)"[^>]*title="[^-]+-\s*([^"]+)"'
    matches = re.findall(pattern, html)
    return [{"url": url, "title": title.strip()} for url, title in matches]


def parse_chapter_content(html: str) -> tuple[str, str]:
    """Extract title and body text from a chapter page.

    Title: from the 'title' attribute of <a class="chapter-title">.
    Body: all <p> tags between the chapter-c div opener and the next chapter-nav div.
    The content regex (.*?)</div> stops at the first nested </div>, so we slice by
    landmark class names instead.
    """
    title_match = re.search(r'class="chapter-title"[^>]*title="[^-]+-\s*([^"]+)"', html)
    if title_match:
        title = title_match.group(1).strip()
    else:
        h2_match = re.search(r'<h2[^>]*>(.*?)</h2>', html, re.DOTALL)
        title = re.sub(r'<[^>]+>', '', h2_match.group(1)).strip() if h2_match else "Không rõ tiêu đề"

    start_match = re.search(r'<div[^>]*class="[^"]*chapter-c[^"]*"[^>]*>', html)
    if not start_match:
        return title, ""

    content_html = html[start_match.end():]
    nav_pos = content_html.find('class="chapter-nav"')
    if nav_pos > 0:
        content_html = content_html[:nav_pos]

    paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', content_html, re.DOTALL)
    body = "\n\n".join(re.sub(r'<[^>]+>', '', p).strip() for p in paragraphs if p.strip())
    return title, body


def save_chapter(num: int, title: str, body: str, dest_dir: Path, prefix: str = "ch") -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    out_path = dest_dir / f"{prefix}_{num:03d}.md"
    out_path.write_text(f"# {title}\n\n{body}\n", encoding="utf-8")
    return out_path


def run_test():
    fixture = TESTS_DIR / "sample_truyenfull.html"
    html = fixture.read_text(encoding="utf-8")

    chapters = parse_chapter_list(html)
    print(f"[test] Found {len(chapters)} chapter links in fixture")

    for i, block_match in enumerate(
        re.finditer(r'<div[^>]+class="chapter-c"[^>]*>(.*?)</div>', html, re.DOTALL), start=1
    ):
        block_html = f'<div class="chapter-c">{block_match.group(1)}</div>'
        title, body = parse_chapter_content(block_html)
        path = save_chapter(i, title, body, TEST_DIR, prefix="test_ch")
        print(f"[test] Written: {path}")

    print("[test] PASS")


def run_inspect():
    """Fetch the first listing page and dump its HTML so you can examine the structure."""
    try:
        import requests
    except ImportError:
        sys.exit("requests not installed — run: pip install requests")

    url = f"{BASE_URL}/trang-1/"
    print(f"[inspect] Fetching {url}")
    resp = requests.get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    print(f"[inspect] Status: {resp.status_code}  Final URL: {resp.url}")
    DUMP_FILE.write_text(resp.text, encoding="utf-8")
    print(f"[inspect] Full HTML saved to: {DUMP_FILE}")

    chapters = parse_chapter_list(resp.text)
    print(f"[inspect] parse_chapter_list found: {len(chapters)} chapters")
    if chapters:
        print(f"[inspect] First 3: {chapters[:3]}")
    else:
        # Show surrounding context to help diagnose regex mismatch
        snippet = resp.text[:3000]
        print("[inspect] No chapters matched. First 3000 chars of HTML:\n")
        print(snippet)


def run_dry_run():
    try:
        import requests
    except ImportError:
        sys.exit("requests not installed — run: pip install requests")

    # Test listing page first
    list_url = f"{BASE_URL}/trang-1/"
    print(f"[dry-run] Fetching chapter list: {list_url}")
    resp = requests.get(list_url, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    chapters = parse_chapter_list(resp.text)
    print(f"[dry-run] Chapters found on page 1: {len(chapters)}")
    if not chapters:
        print("[dry-run] No chapters parsed — run --inspect to examine the raw HTML")
        return
    print(f"[dry-run] First chapter URL: {chapters[0]['url']}")

    # Fetch the first chapter content
    resp = requests.get(chapters[0]["url"], timeout=15, headers={"User-Agent": "Mozilla/5.0"})
    resp.raise_for_status()
    title, body = parse_chapter_content(resp.text)
    print(f"[dry-run] Title: {title}")
    print(f"[dry-run] Body preview:\n{body[:400]}...")


def run_full():
    try:
        import requests
    except ImportError:
        sys.exit("requests not installed — run: pip install requests")

    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0"

    all_chapters: list[dict] = []
    page = 1
    for _ in range(CHAPTER_LIMIT - 1):  # safety limit to avoid infinite loop
        url = f"{BASE_URL}/trang-{page}/"
        print(f"Fetching chapter list page {page}...")
        resp = session.get(url, timeout=15)
        if resp.status_code == 404:
            break
        resp.raise_for_status()
        found = parse_chapter_list(resp.text)
        if not found:
            if page == 1:
                sys.exit(
                    "ERROR: No chapters found on listing page 1. "
                    "The site HTML may have changed.\n"
                    f"Run --inspect to dump the raw HTML: python {__file__} --inspect"
                )
            break
        all_chapters.extend(found)
        page += 1
        time.sleep(REQUEST_DELAY)

    print(f"Total chapters found: {len(all_chapters)}")

    # cache the chapter list to avoid hitting the site again if we need to re-run the content parsing
    list_cache = PROJECT_DIR / "chapter_list_cache.txt"
    list_cache.write_text("\n".join(ch["url"] for ch in all_chapters), encoding="utf-8")
    print(f"Chapter list cached to: {list_cache}")

    chapters_to_scrape = all_chapters[:CHAPTER_LIMIT]
    print(f"Scraping {len(chapters_to_scrape)} chapters...")

    for i, ch in enumerate(chapters_to_scrape, start=1):
        out_path = INPUT_DIR / f"ch_{i:03d}.md"
        if out_path.exists():
            print(f"  [{i}/{CHAPTER_LIMIT}] skip (exists)")
            continue
        resp = session.get(ch["url"], timeout=15)
        resp.raise_for_status()
        title, body = parse_chapter_content(resp.text)
        save_chapter(i, title, body, INPUT_DIR)
        print(f"  [{i}/{CHAPTER_LIMIT}] {title}")
        time.sleep(REQUEST_DELAY)

    print("Done.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--inspect", action="store_true",
                        help="Dump raw HTML of listing page 1 to diagnose parsing issues")
    args = parser.parse_args()

    if args.test:
        run_test()
    elif args.inspect:
        run_inspect()
    elif args.dry_run:
        run_dry_run()
    else:
        confirm = input(f"This will scrape ~{CHAPTER_LIMIT} chapters from truyenfull.vision. Proceed? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
        else:
            run_full()


if __name__ == "__main__":
    main()
