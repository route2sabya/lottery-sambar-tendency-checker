#!/bin/bash
set -euo pipefail

PROJECT="/Users/sabyasachipurkayastha/proj_claude/lottery_by_chance"
VPS="root@187.127.162.86"
VPS_PATH="/var/www/lottery-sambad-checker"
SSH_KEY="/Users/sabyasachipurkayastha/.ssh/id_ed25519"

mkdir -p "$PROJECT/logs"
LOG="$PROJECT/logs/update_$(date +%Y-%m-%d).log"
exec >> "$LOG" 2>&1

echo "==== $(date) ===="
cd "$PROJECT"

echo "Fetching new lottery draws..."
"$PROJECT/.venv/bin/python" update_data.py

echo "Committing to git..."
/usr/bin/git add -A
/usr/bin/git diff --cached --quiet && echo "Nothing new to commit." || \
    /usr/bin/git commit -m "chore: weekly data refresh $(date +%Y-%m-%d)"
/usr/bin/git push origin main

echo "Syncing to VPS..."
/usr/bin/ssh -i "$SSH_KEY" -o StrictHostKeyChecking=no "$VPS" \
    "cd $VPS_PATH && git pull origin main && systemctl restart lottery-sambad-checker"

echo "Done: $(date)"
