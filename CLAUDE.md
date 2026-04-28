# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

`boktrans` is a personal ebook translation workspace that uses AI to produce Vietnamese translations of ebooks. Each book is a self-contained project under `./projects/`.

## Project structure

Each project under `./projects/<book-name>/` follows this layout:

- `input/` — raw source material (original-language text, downloaded HTML, etc.)
- `output/` — translated content and intermediate artifacts (markdown chapters, final epub)
- `pipelines/` — shell scripts, AI prompt logs, or tool configs used to transform input → output
- `TODOs.md` — project summary, status, and remaining tasks (read this first when picking up a project)

## Typical translation workflow

1. **Scrape/extract** source text into `input/`
2. **Translate/edit** chapters into natural-language Vietnamese markdown, saved in `output/`
3. **Review** manually and refine quality
4. **Convert** final markdown to epub (e.g. `pandoc`)

## Tooling notes

- The `.gitignore` is Python-based — Python scripts are the expected automation layer for scraping, processing, and conversion pipelines.
- `pandoc` is the assumed tool for markdown → epub conversion.
- Scripts and prompt histories live in `pipelines/` per-project; check there before writing new automation.

## Pipeline rules

### Testing vs. execution

Every pipeline script must be testable with dummy input without touching real project data:

- Each pipeline must accept a `--test` flag (or equivalent) that runs against a small synthetic sample stored alongside the script in `pipelines/tests/` (e.g. `sample_input.txt`, `sample_chapter.html`).
- Running with `--test` must complete without network calls, API calls, or writes to `input/` or `output/`.
- Automated test runs (`--test` mode) may be triggered freely — they are safe to execute at any time.

Running a pipeline against **real input** is always a manual step:

- Never execute a pipeline on real data without explicit user instruction.
- Before running on real data, display the full command and pipeline content for review and wait for confirmation.
- Writes to `output/` during real runs should be previewed (dry-run or first-item-only) before processing the full dataset.

### Crawled input storage

Scraping pipelines must save the raw crawled content (HTML stripped, plain text only) into the project's `input/` folder in markdown format before any further processing:

- Each scraped chapter is saved as `input/ch_NNN.md` with the format `# <title>\n\n<body paragraphs>`.
- No HTML tags, navigation elements, or ads may appear in `input/` files — strip them during scraping.
- `input/` files are the source of truth for the original content; `output/` files are derived from them.
- Pipelines that transform or translate content must read from `input/`, not re-scrape, to keep processing idempotent.

### AI agent tasks

When a pipeline step requires an AI agent (translation, editing, quality review), implement it as a script-based orchestrator rather than an interactive session:

- Write a Python orchestrator script in `pipelines/` that calls the Claude API (or another LLM API) in a loop, passing each chunk/chapter as a prompt and writing results to `output/`.
- The orchestrator must be re-entrant: track completed items (e.g. a `state.json` sidecar) so it can resume after interruption without re-processing.
- Prompt templates live as separate `.txt` or `.md` files in `pipelines/`, not hard-coded in the script, so they can be reviewed and adjusted independently.
- The orchestrator runs in `--test` mode against `pipelines/tests/` sample data to validate the prompt/output format before real use.

## Style adjustment for converted chapters

When a project has two tiers of source content — a standard translation (high quality, human-edited) and a converted version (low quality, machine-generated) — the AI editing pipeline must produce output that is meaningfully different from its input:

- The goal is not to paraphrase or lightly touch the text. The output must read as if it were translated by the same person who produced the standard chapters — same tone, same sentence rhythm, same choice of Vietnamese register, same handling of names and honorifics.
- Verify that the output differs substantively from the input before saving. If the model returns the same text or only makes superficial changes, treat it as a failure: log it to `state.json["failed"]` and continue to the next chapter rather than writing unchanged content to `output/`.
- The prompt must make this expectation explicit. Include concrete examples from the standard chapters and instruct the model to rewrite — not copy — the converted text.
- After a dry-run, manually diff the input and output before committing to the full batch. If the diff is trivial, fix the prompt first.

## Working on a project

- Always read the project's `TODOs.md` first for context, status, and task breakdown.
- Output chapters go in `output/` as markdown files; one file per chapter is preferred.
- When writing or editing translated text, match the style and register of the already-translated reference chapters noted in `TODOs.md`.
