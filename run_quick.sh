#!/usr/bin/env bash
# run_quick.sh  —  vinny-stack convenience launcher
# Usage: ./run_quick.sh <input> [preset]
#   preset: ingest (default) | full | ocr | url
#
# Examples:
#   ./run_quick.sh ~/notes/meeting.md
#   ./run_quick.sh ~/Desktop/scan.pdf       ocr
#   ./run_quick.sh https://example.com/doc  url
#   ./run_quick.sh ~/data/corpus.txt        full

set -euo pipefail

INPUT="${1:-}"
PRESET="${2:-ingest}"

if [[ -z "$INPUT" ]]; then
  echo "Usage: ./run_quick.sh <file_or_url> [ingest|full|ocr|url]"
  exit 1
fi

case "$PRESET" in
  ingest)
    STAGES="capture,chunk,embed,store"
    ;;
  full)
    STAGES="all"
    ;;
  ocr)
    STAGES="capture,ocr,chunk,embed,store"
    ;;
  url)
    STAGES="capture,chunk,embed,summarize,store"
    ;;
  *)
    # Treat preset as a literal comma-separated stage list
    STAGES="$PRESET"
    ;;
esac

echo "[vinny-stack] input=$INPUT preset=$PRESET stages=$STAGES"
exec python pipeline.py --input "$INPUT" --stages "$STAGES"
