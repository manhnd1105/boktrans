"""AI translation: loops over input/*.md, translates each to output/*.md."""
import os
import sys
import time
from collections.abc import Callable
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
PROMPT_FILE = SCRIPT_DIR / "prompts" / "translate_vi.md"

MODELS = [
    "gemini/gemini-2.5-flash",
    "kc/stepfun/step-3.5-flash:free",
    "kc/openrouter/free",
    "kc/kilo-auto/free",
]
MODEL_NAME = os.environ.get("MODEL_NAME", MODELS[2])
MODEL_PROVIDER = os.environ.get("MODEL_PROVIDER", "openai")
MODEL_BASE_URL = os.environ.get("MODEL_BASE_URL", "http://host.docker.internal:20128/v1")
MODEL_API_KEY = os.environ.get("MODEL_API_KEY", "anything")


def parse_chapters_arg(chapters_arg: str) -> set[int] | None:
    """Parse '1-50' or '1,2,3' into a set of ints; None means no filter."""
    if not chapters_arg:
        return None
    result: set[int] = set()
    for part in chapters_arg.split(","):
        part = part.strip()
        if "-" in part:
            lo, hi = part.split("-", 1)
            result.update(range(int(lo), int(hi) + 1))
        else:
            result.add(int(part))
    return result


def _make_model(model_name: str):
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


def _call_with_fallback(prompt_text: str) -> str:
    from langchain_core.messages import HumanMessage
    last_exc: Exception | None = None
    for model_name in MODELS:
        try:
            model = _make_model(model_name)
            response = model.invoke([HumanMessage(content=prompt_text)])
            return response.content.strip()
        except Exception as e:
            last_exc = e
    raise RuntimeError(f"All models exhausted. Last error: {last_exc}") from last_exc


def _is_too_short(original: str, translated: str) -> bool:
    return len(translated.strip()) < len(original.strip()) * 0.5


def translate_all(
    input_dir: Path,
    output_dir: Path,
    progress_cb: Callable[[str], None] = print,
    chapter_filter: set[int] | None = None,
) -> int:
    """Translate chapters in input_dir to output_dir. Returns count of translated files."""
    import re
    template = PROMPT_FILE.read_text(encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)

    all_files = sorted(input_dir.glob("ch_*.md"))
    if chapter_filter is not None:
        chapter_files = [
            p for p in all_files
            if (m := re.search(r'ch_(\d+)\.md$', p.name)) and int(m.group(1)) in chapter_filter
        ]
    else:
        chapter_files = all_files
    total = len(chapter_files)
    if total == 0:
        raise RuntimeError(f"No chapters found in {input_dir}")

    progress_cb("Configured model: %s (%s, %s)" % (MODEL_NAME, MODEL_PROVIDER, MODEL_BASE_URL))
    translated = 0
    for i, path in enumerate(chapter_files, start=1):
        out = output_dir / path.name
        if out.exists():
            progress_cb(f"  [{i}/{total}] {path.name}: already translated, skipping")
            translated += 1
            continue

        chapter_text = path.read_text(encoding="utf-8")
        prompt = template.replace("{{CHAPTER_TEXT}}", chapter_text)

        progress_cb(f"  [{i}/{total}] {path.name}: translating ({len(chapter_text)} chars)...")
        t0 = time.monotonic()
        try:
            result = _call_with_fallback(prompt)
            elapsed = time.monotonic() - t0
            if _is_too_short(chapter_text, result):
                progress_cb(f"  [{i}/{total}] {path.name}: translation too short, skipping")
                continue
            out.write_text(result + "\n", encoding="utf-8")
            translated += 1
            progress_cb(f"  [{i}/{total}] {path.name}: done ({len(result)} chars, {elapsed:.1f}s)")
        except Exception as e:
            elapsed = time.monotonic() - t0
            progress_cb(f"  [{i}/{total}] {path.name}: FAILED after {elapsed:.1f}s — {e}")
            continue

    return translated
