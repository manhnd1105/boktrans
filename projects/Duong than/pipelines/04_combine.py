#!/usr/bin/env python3
"""
Combine all chapter markdown files into a single document.

Usage:
  python 04_combine.py --test   # combine test fixture files, print to stdout
  python 04_combine.py          # combine output/chapters/ch_001..ch_781 → output/duong_than_full.md
"""
import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
INPUT_DIR = PROJECT_DIR / "input"
OUTPUT_DIR = PROJECT_DIR / "output" / "chapters"  # test chapter output only
COMBINED_OUTPUT = PROJECT_DIR / "output" / "duong_than_full.md"

SEPARATOR = "\n\n---\n\n"
CONVERT_MARKER = "<!-- source: convert -->"


def sorted_by_num(paths: list[Path]) -> list[Path]:
    return sorted(paths, key=lambda p: int(re.search(r'(\d+)', p.name).group(1)))


def resolve_chapter_paths() -> list[Path]:
    """
    For each chapter number, prefer the AI-edited version from output/chapters/
    if it exists (no convert marker), otherwise fall back to input/.
    """
    input_files = {int(re.search(r'(\d+)', p.name).group(1)): p
                   for p in INPUT_DIR.glob("ch_*.md")}
    output_files = {int(re.search(r'(\d+)', p.name).group(1)): p
                    for p in OUTPUT_DIR.glob("ch_*.md")}
    all_nums = sorted(input_files.keys() | output_files.keys())
    result = []
    for num in all_nums:
        out = output_files.get(num)
        if out and CONVERT_MARKER not in out.read_text(encoding="utf-8"):
            result.append(out)
        elif num in input_files:
            result.append(input_files[num])
    return result


def combine(paths: list[Path]) -> str:
    parts = []
    for path in paths:
        text = path.read_text(encoding="utf-8").replace(CONVERT_MARKER, "").strip()
        if text:
            parts.append(text)
    return SEPARATOR.join(parts)


def run_test():
    test_files = sorted_by_num(list(OUTPUT_DIR.glob("test_ch_*.md")))
    if not test_files:
        print("[test] No test_ch_*.md files found — run pipeline 01/02 --test first")
        sys.exit(1)
    result = combine(test_files)
    print(f"[test] Combined {len(test_files)} test chapter(s):")
    print(result)
    print("\n[test] PASS — no file written")


def run_full():
    paths = resolve_chapter_paths()
    if not paths:
        sys.exit("No chapters found in input/ — run pipelines 01 and 02 first.")

    pending_convert = [p for p in paths if CONVERT_MARKER in p.read_text(encoding="utf-8")]
    if pending_convert:
        print(f"Warning: {len(pending_convert)} chapter(s) are still raw convert "
              "(not yet AI-edited). They will be included as-is.")
        confirm = input("Continue anyway? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
            return

    result = combine(paths)
    COMBINED_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    COMBINED_OUTPUT.write_text(result + "\n", encoding="utf-8")
    print(f"Written: {COMBINED_OUTPUT} ({len(paths)} chapters, {len(result):,} chars)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    args = parser.parse_args()

    if args.test:
        run_test()
    else:
        run_full()


if __name__ == "__main__":
    main()
