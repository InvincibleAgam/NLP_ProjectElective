#!/usr/bin/env bash
# Download the source documents the parser expects.
#
# The consolidated Basel Framework is the primary corpus: one PDF carrying every
# standard with its paragraph numbering intact (CRE20.68 and so on), which is
# what lets extracted rules cite something checkable. The four supporting
# publications are the original standards behind chapters that the consolidated
# text compresses.
set -euo pipefail

UA="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/125.0 Safari/537.36"
DEST="${1:-data/basel}"
mkdir -p "$DEST"

fetch () {
  local url="$1" out="$DEST/$2"
  if [[ -s "$out" ]]; then echo "have  $2"; return; fi
  echo "get   $2"
  curl -fsSL --max-time 600 -A "$UA" "$url" -o "$out"
  head -c 5 "$out" | grep -q '%PDF' || { echo "  !! not a PDF: $2" >&2; rm -f "$out"; exit 1; }
}

fetch https://www.bis.org/baselframework/BaselFramework.pdf BaselFramework.pdf
fetch https://www.bis.org/bcbs/publ/d424.pdf   d424.pdf      # finalising post-crisis reforms
fetch https://www.bis.org/bcbs/publ/d295.pdf   d295.pdf      # NSFR
fetch https://www.bis.org/publ/bcbs189.pdf     bcbs189.pdf   # Basel III capital framework
fetch https://www.bis.org/publ/bcbs238.pdf     bcbs238.pdf   # LCR

echo
echo "next: .venv/bin/python src/ingest/parse_basel.py $DEST/BaselFramework.pdf $DEST/paragraphs.jsonl"
