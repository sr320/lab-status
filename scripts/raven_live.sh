#!/bin/bash
# Runs from sr320's crontab on raven every 5 minutes:
#   */5 * * * * $HOME/lab-status-live/raven_live.sh >> $HOME/lab-status-live/raven_live.log 2>&1
# Takes an htop-style snapshot and force-pushes it as the only commit on the
# raven-live branch of sr320/lab-status, using a deploy key that can write to
# that repo only. Raven isn't reachable from outside UW, so it has to push.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
KEY="$HOME/.ssh/lab_status_deploy"
REPO="git@github.com:sr320/lab-status.git"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 "$DIR/raven_live.py" "$WORK/raven-live.json"

cd "$WORK"
git init -q -b raven-live
git -c user.name="raven" -c user.email="sr320@uw.edu" add raven-live.json
git -c user.name="raven" -c user.email="sr320@uw.edu" commit -qm "raven snapshot"
GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes" \
  timeout 60 git push -qf "$REPO" raven-live
