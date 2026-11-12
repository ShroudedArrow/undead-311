#!/usr/bin/env bash
# Collects GitHub settings for the audit using a READ-ONLY token (GH_TOKEN=$GITHUB_AUDIT_TOKEN).
# Writes JSON to ~/logs/github-settings.json. Never changes anything. Errors are recorded, not fatal.
set -u
OWNER="${1:?usage: collect_github_settings.sh <github-username>}"
OUT="$HOME/logs/github-settings.json"; mkdir -p "$HOME/logs"
export GH_TOKEN="${GITHUB_AUDIT_TOKEN:?set GITHUB_AUDIT_TOKEN}"
q() { gh api "$1" 2>&1 || true; }
{
  echo "{"
  for R in undead-311 undead-311-crew boston-311-power undead-311-data undead-311-ops; do
    echo "\"$R\": {"
    echo "\"repo\": $(q repos/$OWNER/$R | jq -c '{private, visibility, license: .license.spdx_id, default_branch, has_issues, security: .security_and_analysis}' 2>/dev/null || echo null),"
    echo "\"main_protection\": $(q repos/$OWNER/$R/branches/main/protection | jq -c . 2>/dev/null || echo '"unavailable"'),"
    echo "\"deploy_keys\": $(q repos/$OWNER/$R/keys | jq -c '[.[] | {title, read_only}]' 2>/dev/null || echo '"unavailable"'),"
    echo "\"labels\": $(q repos/$OWNER/$R/labels?per_page=100 | jq -c '[.[].name]' 2>/dev/null || echo '"unavailable"')"
    echo "},"
  done
  echo "\"collected_at\": \"$(date -u +%FT%TZ)\""
  echo "}"
} > "$OUT"
echo "Wrote $OUT"
