#!/bin/bash
# Runs from sr320's crontab on raven every 15 minutes:
#   3,18,33,48 * * * * $HOME/lab-status-live/trigger_scrape.sh >> $HOME/lab-status-live/trigger_scrape.log 2>&1
# Starts the "Scrape lab calendar" workflow, because GitHub delays the
# workflow's own schedule by hours. It force-pushes an empty commit on top of
# main to the scrape-trigger branch with the same deploy key raven_live.sh
# uses; the workflow runs on pushes to that branch (and checks out main).
# The commit has to sit on main because GitHub reads the workflow file from
# the pushed commit.
set -euo pipefail

KEY="$HOME/.ssh/lab_status_deploy"
REPO="git@github.com:sr320/lab-status.git"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

export GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes"
cd "$WORK"
git init -q
timeout 60 git fetch -q --depth 1 "$REPO" main
git -c user.name="raven" -c user.email="sr320@uw.edu" commit-tree FETCH_HEAD^{tree} -p FETCH_HEAD \
  -m "Trigger calendar scrape $(date -u +%FT%TZ)" > commit
timeout 60 git push -qf "$REPO" "$(cat commit):refs/heads/scrape-trigger"
