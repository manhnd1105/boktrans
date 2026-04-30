#!/usr/bin/env python3
"""
AI editing orchestrator — refines chapters 499-781 to match reference style.
Uses LangChain init_chat_model pointed at a self-hosted OpenAI-compatible endpoint.

Usage:
  python 03_edit_orchestrator.py --test                      # mock run on fixture, no API call, no writes
  python 03_edit_orchestrator.py --dry-run                   # process one real chapter, print result, no writes
  python 03_edit_orchestrator.py --dry-run --chapters 500-510
  python 03_edit_orchestrator.py                             # MANUAL: process all pending convert chapters
  python 03_edit_orchestrator.py --chapters 500-600          # MANUAL: process chapters 500–600 only
  python 03_edit_orchestrator.py --chapters 500,502,510      # MANUAL: process specific chapters

Requirements: pip install langchain langchain-openai
"""
import argparse
import difflib
import json
import os
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROJECT_DIR = SCRIPT_DIR.parent
INPUT_DIR = PROJECT_DIR / "input"
OUTPUT_DIR = PROJECT_DIR / "output" / "chapters"
TESTS_DIR = SCRIPT_DIR / "tests"
PROMPT_FILE = SCRIPT_DIR / "prompts" / "edit_style_match.md"
STATE_FILE = SCRIPT_DIR / "state.json"

# Model config — override via environment variables
MODELS = [
    "gemini/gemini-2.5-flash",
    "kc/stepfun/step-3.5-flash:free",
    "kc/openrouter/free",
    "kc/kilo-auto/free",
]
MODEL_NAME = os.environ.get("MODEL_NAME", MODELS[2])
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "openai")
MODEL_BASE_URL = os.environ.get("MODEL_BASE_URL", "http://localhost:20128/v1")
MODEL_API_KEY = os.environ.get("MODEL_API_KEY", "anything")

REFERENCE_CHAPTERS = [1, 250, 498]  # injected as style examples
CONVERT_MARKER = "<!-- source: convert -->"


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {"completed": [], "failed": []}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def build_reference_text(chapters: list[int]) -> str:
    parts = []
    for num in chapters:
        path = INPUT_DIR / f"ch_{num:03d}.md"
        if path.exists():
            parts.append(f"--- Chương {num} ---\n{path.read_text(encoding='utf-8')}")
    return "\n\n".join(parts)


def build_prompt(template: str, reference_text: str, chapter_text: str) -> str:
    return (template
            .replace("{{REFERENCE_TEXT}}", reference_text)
            .replace("{{CHAPTER_TEXT}}", chapter_text))


SIMILARITY_THRESHOLD = 0.70  # reject if output is more than 70% similar to input


def is_too_similar(original: str, edited: str) -> bool:
    a = re.sub(r'<!--.*?-->', '', original).strip()
    b = re.sub(r'<!--.*?-->', '', edited).strip()
    ratio = difflib.SequenceMatcher(None, a, b).ratio()
    return ratio > SIMILARITY_THRESHOLD


def parse_chapters_arg(chapters_arg: str) -> set[int] | None:
    """Parse '500-600' or '500,501,502' into a set of ints; None means no filter."""
    if not chapters_arg:
        return None
    result = set()
    for part in chapters_arg.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            result.update(range(int(lo), int(hi) + 1))
        else:
            result.add(int(part))
    return result


def pending_chapters(chapter_filter: set[int] | None = None) -> list[int]:
    state = load_state()
    done = set(state["completed"])  # failed chapters are retried on the next run
    result = []
    for path in sorted(INPUT_DIR.glob("ch_*.md")):
        if CONVERT_MARKER not in path.read_text(encoding="utf-8"):
            continue
        match = re.search(r'ch_(\d+)\.md$', path.name)
        if match:
            num = int(match.group(1))
            if num not in done and (chapter_filter is None or num in chapter_filter):
                result.append(num)
    return result


def make_model(model_name: str):
    """Instantiate the LangChain chat model for the given model name."""
    try:
        from langchain.chat_models import init_chat_model
    except ImportError:
        sys.exit("langchain not installed — run: pip install langchain langchain-openai")
    return init_chat_model(
        model=model_name,
        model_provider=MODEL_PROVIDER,
        base_url=MODEL_BASE_URL,
        openai_api_key=MODEL_API_KEY,
    )


def call_model(model, template: str, reference_text: str, chapter_text: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage
    prompt = build_prompt(template, reference_text, chapter_text)
    messages = [
        SystemMessage(content="Bạn là biên tập viên văn học chuyên nghiệp chỉnh sửa truyện tiếng Việt."),
        HumanMessage(content=prompt),
    ]
    response = model.invoke(messages)
    return response.content.strip()


def call_model_with_fallback(template: str, reference_text: str, chapter_text: str) -> str:
    """Try each model in MODELS in order; return the first successful response."""
    last_exc: Exception | None = None
    for model_name in MODELS:
        try:
            model = make_model(model_name)
            result = call_model(model, template, reference_text, chapter_text)
            if model_name != MODEL_NAME:
                print(f"[fallback: used {model_name}]", end=" ")
            return result
        except Exception as e:
            print(f"\n[fallback] {model_name} failed: {e}", end=" ")
            last_exc = e
    raise RuntimeError(f"All models exhausted. Last error: {last_exc}") from last_exc


def run_test():
    """Process the fixture with a rule-based mock edit — no API call, no file writes."""
    fixture = TESTS_DIR / "sample_convert.md"
    chapter_text = fixture.read_text(encoding="utf-8")
    template = PROMPT_FILE.read_text(encoding="utf-8")

    reference_text = "[mock reference — not loaded in test mode]"
    prompt = build_prompt(template, reference_text, chapter_text)

    edited = chapter_text.replace(CONVERT_MARKER, "").strip()
    edited = re.sub(r'\bko\b', 'không', edited)
    edited = re.sub(r'\b1\b', 'một', edited)
    edited = re.sub(r'\b2\b', 'hai', edited)

    print("[test] Prompt preview (first 200 chars):")
    print(prompt[:200], "...\n")
    print("[test] Mock edited output:")
    print(edited)
    print("\n[test] PASS — no API calls made, state.json not modified")


def run_dry_run(chapter_filter: set[int] | None = None):
    """Process one real chapter with the model, print result, no file writes."""
    pending = pending_chapters(chapter_filter)
    if not pending:
        print("[dry-run] No pending convert chapters found.")
        return

    num = pending[0]
    path = INPUT_DIR / f"ch_{num:03d}.md"
    chapter_text = path.read_text(encoding="utf-8")
    template = PROMPT_FILE.read_text(encoding="utf-8")
    reference_text = build_reference_text(REFERENCE_CHAPTERS)

    print(f"[dry-run] Chapter {num} ({len(chapter_text)} chars), "
          f"reference {len(reference_text)} chars")
    print(f"[dry-run] Model: {MODEL_NAME} (with fallback) @ {MODEL_BASE_URL}")

    edited = call_model_with_fallback(template, reference_text, chapter_text)

    print(f"\n[dry-run] Edited output (first 500 chars):\n{edited[:500]}...")
    print("\n[dry-run] File NOT written — dry-run mode")


def run_full(chapter_filter: set[int] | None = None):
    template = PROMPT_FILE.read_text(encoding="utf-8")
    reference_text = build_reference_text(REFERENCE_CHAPTERS)
    if not reference_text.strip():
        sys.exit("Reference chapters not found. Run pipeline 01 first.")

    state = load_state()
    pending = pending_chapters(chapter_filter)

    print(f"Pending chapters: {len(pending)}")
    print(f"Model: {MODEL_NAME} (with fallback) @ {MODEL_BASE_URL}")
    if not pending:
        print("Nothing to do.")
        return

    for num in pending:
        path = INPUT_DIR / f"ch_{num:03d}.md"
        chapter_text = path.read_text(encoding="utf-8")
        retrying = num in state["failed"]
        label = "Retrying" if retrying else "Editing"
        if retrying:
            state["failed"].remove(num)
            save_state(state)
        print(f"  {label} chapter {num}...", end=" ", flush=True)
        try:
            edited = call_model_with_fallback(template, reference_text, chapter_text)
            if is_too_similar(chapter_text, edited):
                state["failed"].append(num)
                save_state(state)
                print("FAILED: output too similar to input (model did not rewrite)")
                continue
            out_path = OUTPUT_DIR / f"ch_{num:03d}.md"
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_text(edited + "\n", encoding="utf-8")
            state["completed"].append(num)
            save_state(state)
            print("done")

        except Exception as e:
            state["failed"].append(num)
            save_state(state)
            print(f"FAILED: {e}")

    print(f"\nCompleted: {len(state['completed'])}, Failed: {len(state['failed'])}")
    if state["failed"]:
        print(f"Failed chapters: {state['failed']} — re-run to retry")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument(
        "--chapters",
        metavar="RANGE",
        help="Limit to specific chapters: '500-600' or '500,501,502'",
    )
    args = parser.parse_args()

    chapter_filter = parse_chapters_arg(args.chapters)

    if args.test:
        run_test()
    elif args.dry_run:
        run_dry_run(chapter_filter)
    else:
        pending = pending_chapters(chapter_filter)
        print(f"Chapters pending AI editing: {len(pending)}")
        confirm = input("Review prompts/edit_style_match.md first. Proceed with real API calls? [y/N] ")
        if confirm.lower() != "y":
            print("Aborted.")
        else:
            run_full(chapter_filter)


if __name__ == "__main__":
    main()
