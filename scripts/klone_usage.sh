#!/bin/bash
# Runs hourly from sr320's scrontab on klone (`scrontab -e`):
#   #SCRON --account=srlab --partition=ckpt --time=00:10:00 --mem=1G
#   7 * * * * $HOME/lab-status-live/klone_usage.sh >> $HOME/lab-status-live/klone_usage.log 2>&1
# Collects per-user Slurm usage for the lab's accounts and force-pushes it as
# the only commit on the klone-usage branch of sr320/lab-status, using a
# deploy key that can write to that repo only. Klone needs Duo for SSH, so
# nothing outside can pull this; it has to push.
set -euo pipefail

DIR="$(cd "$(dirname "$0")" && pwd)"
KEY="$HOME/.ssh/lab_status_klone_deploy"
REPO="git@github.com:sr320/lab-status.git"
# Lab members to name even when their jobs ran only under a shared account like coenv.
export KLONE_USERS="${KLONE_USERS:-}"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

python3 "$DIR/klone_usage.py" "$WORK/klone-usage.json"

cd "$WORK"
git init -q -b klone-usage
git -c user.name="klone" -c user.email="sr320@uw.edu" add klone-usage.json
git -c user.name="klone" -c user.email="sr320@uw.edu" commit -qm "klone usage snapshot"
GIT_SSH_COMMAND="ssh -i $KEY -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=accept-new" \
  timeout 60 git push -qf "$REPO" klone-usage
