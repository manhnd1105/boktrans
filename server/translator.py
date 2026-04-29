"""AI translation: loops over input/*.md, translates each to output/*.md."""
import os
import sys
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
MODEL_BASE_URL = os.environ.get("MODEL_BASE_URL", "http://localhost:20128/v1")
MODEL_API_KEY = os.environ.get("MODEL_API_KEY", "anything")


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
) -> int:
    """Translate all chapters in input_dir to output_dir. Returns count of translated files."""
    template = PROMPT_FILE.read_text(encoding="utf-8")
    output_dir.mkdir(parents=True, exist_ok=True)

    chapter_files = sorted(input_dir.glob("ch_*.md"))
    total = len(chapter_files)
    if total == 0:
        raise RuntimeError(f"No chapters found in {input_dir}")

    translated = 0
    for i, path in enumerate(chapter_files, start=1):
        out = output_dir / path.name
        if out.exists():
            translated += 1
            continue

        chapter_text = path.read_text(encoding="utf-8")
        prompt = template.replace("{{CHAPTER_TEXT}}", chapter_text)

        try:
            result = _call_with_fallback(prompt)
            if _is_too_short(chapter_text, result):
                progress_cb(f"  [{i}/{total}] {path.name}: translation too short, skipping")
                continue
            out.write_text(result + "\n", encoding="utf-8")
            translated += 1
        except Exception as e:
            progress_cb(f"  [{i}/{total}] {path.name}: FAILED — {e}")
            continue

        if i % 50 == 0 or i == total:
            progress_cb(f"Translated {i} / {total} chapters...")

    return translated
