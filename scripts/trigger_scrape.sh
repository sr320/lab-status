#!/bin/bash
# Runs from sr320's crontab on raven every 15 minutes:
#   3,18,33,48 * * * * $HOME/lab-status-live/trigger_scrape.sh >> $HOME/lab-status-live/trigger_scrape.log 2>&1
# Starts the "Scrape lab calendar" workflow, because GitHub delays the
# workflow's own schedule by hours. It force-pushes a one-file commit to the
# scrape-trigger branch with the same deploy key raven_live.sh uses; the
# workflow runs on pushes to that branch (and checks out main).
set -euo pipefail

KEY="$HOME/.ssh/lab_status_deploy"
REPO="git@github.com:sr320/lab-status.git"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

cd "$WORK"
date -u +%FT%TZ > trigger
git init -q -b scrape-trigger
git -c user.name="raven" -c user.email="sr320@uw.edu" add trigger
git -c user.name="raven" -c user.email="sr320@uw.edu" commit -qm "Trigger calendar scrape"
GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes" \
  timeout 60 git push -qf "$REPO" scrape-trigger
