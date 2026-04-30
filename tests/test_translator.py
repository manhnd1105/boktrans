"""Integration tests for translator.py (LLM calls mocked)."""
from pathlib import Path
from unittest.mock import patch

import pytest

import translator as tr

TRANSLATED = "# Chương 1: Tiêu đề\n\nĐây là bản dịch tiếng Việt hoàn chỉnh và đầy đủ nội dung chương."


def _write_chapter(directory: Path, num: int, body: str = "Nội dung gốc đủ dài để vượt ngưỡng kiểm tra chất lượng.") -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    p = directory / f"ch_{num:03d}.md"
    p.write_text(f"# Chương {num}: Tiêu đề\n\n{body}\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_translate_all_creates_output_files(tmp_path):
    inp, out = tmp_path / "input", tmp_path / "output"
    _write_chapter(inp, 1)
    _write_chapter(inp, 2)

    with patch("translator._call_with_fallback", return_value=TRANSLATED):
        count = tr.translate_all(inp, out)

    assert count == 2
    assert (out / "ch_001.md").exists()
    assert (out / "ch_002.md").exists()


def test_translate_all_output_content(tmp_path):
    inp, out = tmp_path / "input", tmp_path / "output"
    _write_chapter(inp, 1)

    with patch("translator._call_with_fallback", return_value=TRANSLATED):
        tr.translate_all(inp, out)

    assert (out / "ch_001.md").read_text(encoding="utf-8").strip() == TRANSLATED.strip()


def test_translate_all_skips_already_translated(tmp_path):
    inp, out = tmp_path / "input", tmp_path / "output"
    out.mkdir(parents=True)
    _write_chapter(inp, 1)
    _write_chapter(inp, 2)
    (out / "ch_001.md").write_text("existing", encoding="utf-8")

    call_count = [0]
    def fake_call(_):
        call_count[0] += 1
        return TRANSLATED

    with patch("translator._call_with_fallback", side_effect=fake_call):
        tr.translate_all(inp, out)

    assert call_count[0] == 1  # only ch_002 translated


def test_translate_all_raises_when_no_input_chapters(tmp_path):
    inp = tmp_path / "input"
    inp.mkdir()
    with pytest.raises(RuntimeError, match="No chapters found"):
        tr.translate_all(inp, tmp_path / "output")


# ---------------------------------------------------------------------------
# Quality gate
# ---------------------------------------------------------------------------

def test_translate_all_skips_too_short_output(tmp_path):
    inp, out = tmp_path / "input", tmp_path / "output"
    _write_chapter(inp, 1)

    with patch("translator._call_with_fallback", return_value="Quá ngắn."):
        tr.translate_all(inp, out)

    assert not (out / "ch_001.md").exists()


def test_is_too_short_rejects_short_output():
    assert tr._is_too_short("A" * 100, "B" * 40) is True


def test_is_too_short_accepts_adequate_output():
    assert tr._is_too_short("A" * 100, "B" * 60) is False


def test_is_too_short_at_exact_threshold():
    assert tr._is_too_short("A" * 100, "B" * 50) is False


# ---------------------------------------------------------------------------
# Error resilience
# ---------------------------------------------------------------------------

def test_translate_all_continues_after_model_failure(tmp_path):
    inp, out = tmp_path / "input", tmp_path / "output"
    _write_chapter(inp, 1)
    _write_chapter(inp, 2)

    call_count = [0]
    def fake_call(_):
        call_count[0] += 1
        if call_count[0] == 1:
            raise RuntimeError("Model error")
        return TRANSLATED

    messages = []
    with patch("translator._call_with_fallback", side_effect=fake_call):
        tr.translate_all(inp, out, progress_cb=messages.append)

    assert not (out / "ch_001.md").exists()
    assert (out / "ch_002.md").exists()
    assert any("FAILED" in m for m in messages)


# ---------------------------------------------------------------------------
# Prompt injection
# ---------------------------------------------------------------------------

def test_translate_all_includes_chapter_text_in_prompt(tmp_path):
    inp, out = tmp_path / "input", tmp_path / "output"
    _write_chapter(inp, 1, body="UniqueMarker_XYZ789")

    captured = []
    def fake_call(prompt):
        captured.append(prompt)
        return TRANSLATED

    with patch("translator._call_with_fallback", side_effect=fake_call):
        tr.translate_all(inp, out)

    assert "UniqueMarker_XYZ789" in captured[0]
