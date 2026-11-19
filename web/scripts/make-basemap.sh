#!/usr/bin/env bash
# Rebuild the self-hosted basemap extract web/public/tiles/boston.pmtiles (REQ-WEB-MAP.1, tech.md: no runtime third-party requests).
#
# The map's pan limits (BOSTON_BOUNDS in web/src/map/style.ts) equal BBOX below, so the view can never leave the area the tiles draw.
# Change both together. Greater Boston (the Route 128 ring) plus a margin: about half a degree west of downtown, 0.3 degrees
# north and south, out to sea in the east. At maxzoom 13 the file is about 18 MB (the city-only extract was 4.8 MB).
#
# Needs the go-pmtiles CLI. It is a build tool only, installed into the gitignored .local-data folder:
#   GOBIN="$PWD/.local-data/go/bin" go install github.com/protomaps/go-pmtiles@v1.31.2
# Usage (from the repo root): web/scripts/make-basemap.sh [YYYYMMDD]   (a Protomaps daily build; default 20261118)
set -euo pipefail
BUILD="${1:-20261118}"
BBOX="-71.55,42.05,-70.65,42.65"
MAXZOOM=13
ROOT="$(git rev-parse --show-toplevel)"
PMTILES="${PMTILES:-$ROOT/.local-data/go/bin/go-pmtiles}"
OUT="$ROOT/web/public/tiles/boston.pmtiles"
TMP="$OUT.tmp"
"$PMTILES" extract "https://build.protomaps.com/$BUILD.pmtiles" "$TMP" --bbox="$BBOX" --maxzoom="$MAXZOOM"
mv "$TMP" "$OUT"
"$PMTILES" show "$OUT" | head -20
