#!/bin/bash
# Runs from sr320's crontab on raven every 15 minutes:
#   */15 * * * * $HOME/lab-status-live/trigger_scrape.sh >> $HOME/lab-status-live/trigger_scrape.log 2>&1
# Starts the "Scrape lab calendar" workflow, because GitHub delays the
# workflow's own */15 schedule by hours. The token is a fine-grained PAT
# limited to sr320/lab-status with only "Actions: Read and write".
set -euo pipefail

TOKEN_FILE="$HOME/.config/lab-status/dispatch_token"
URL="https://api.github.com/repos/sr320/lab-status/actions/workflows/in-lab.yml/dispatches"

code=$(timeout 60 curl -s -o /dev/null -w '%{http_code}' -X POST "$URL" \
  -H "Accept: application/vnd.github+json" \
  -H "Authorization: Bearer $(cat "$TOKEN_FILE")" \
  -d '{"ref":"main"}')
if [ "$code" != 204 ]; then
  echo "$(date -u +%FT%TZ) dispatch failed: HTTP $code"
  exit 1
fi
