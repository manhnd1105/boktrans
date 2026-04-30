#!/usr/bin/env bash
# Convert the combined markdown to EPUB using pandoc.
#
# Usage:
#   bash 05_to_epub.sh          # convert output/duong_than_full.md → output/duong_than.epub
#   bash 05_to_epub.sh --test   # convert a 2-chapter sample → output/test.epub

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
OUTPUT_DIR="$PROJECT_DIR/output"

if ! command -v pandoc &>/dev/null; then
  echo "Error: pandoc is not installed. Install it with your package manager." >&2
  exit 1
fi

if [[ "${1:-}" == "--test" ]]; then
  SAMPLE="$OUTPUT_DIR/test_sample.md"
  if compgen -G "$OUTPUT_DIR/chapters/test_ch_*.md" > /dev/null 2>&1; then
    cat "$OUTPUT_DIR"/chapters/test_ch_*.md > "$SAMPLE"
  else
    printf "# Chương Test 1\n\nNội dung chương kiểm tra.\n\n---\n\n# Chương Test 2\n\nNội dung chương kiểm tra hai.\n" > "$SAMPLE"
  fi
  pandoc "$SAMPLE" \
    --from markdown-yaml_metadata_block \
    --metadata title="Dương Thần [TEST]" \
    --metadata lang=vi \
    -o "$OUTPUT_DIR/test.epub"
  rm -f "$SAMPLE"
  echo "[test] Written: $OUTPUT_DIR/test.epub"
  echo "[test] PASS"
else
  INPUT="$OUTPUT_DIR/duong_than_full.md"
  if [[ ! -f "$INPUT" ]]; then
    echo "Error: $INPUT not found — run pipeline 04 first." >&2
    exit 1
  fi
  pandoc "$INPUT" \
    --from markdown-yaml_metadata_block \
    --metadata title="Dương Thần" \
    --metadata author="Dịch thuật AI" \
    --metadata lang=vi \
    --toc \
    -o "$OUTPUT_DIR/duong_than.epub"
  echo "Written: $OUTPUT_DIR/duong_than.epub"
fi
