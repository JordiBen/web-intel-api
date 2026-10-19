#!/usr/bin/env bash
# Copy the core (Apify-independent) logic of each Actor into engines/<name>/ as importable packages.
set -euo pipefail
# WARNING: engines/links/crawler.py and engines/pdf/extract.py carry API-only changes (time budgets, link cap,
# per-host fairness, OCR downscale/timeout, text-layer fast path). Port them to the Actors first, or re-apply after syncing.
ROOT=$(cd "$(dirname "$0")/.." && pwd)
SRC=${ACTORS_DIR:-/workspace/apify/actors}
declare -A MAP=( [health]=website-health-audit [links]=broken-link-checker [markdown]=page-to-markdown [pdf]=pdf-ocr-extractor [tech]=website-tech-detector )
for name in "${!MAP[@]}"; do
  d="$ROOT/engines/$name"; rm -rf "$d"; mkdir -p "$d"
  for f in "$SRC/${MAP[$name]}"/src/*.py; do
    b=$(basename "$f"); [[ "$b" == main.py || "$b" == __main__.py ]] && continue
    cp "$f" "$d/"
  done
  touch "$d/__init__.py"
done
rm -rf "$ROOT/engines/data"; cp -r "$SRC/website-tech-detector/data" "$ROOT/engines/data"
touch "$ROOT/engines/__init__.py"
echo synced
