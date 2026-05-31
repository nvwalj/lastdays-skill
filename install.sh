#!/usr/bin/env bash
# Symlink the lastdays skill into ~/.claude/skills (or a path you pass as $1).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC="$HERE/skills/lastdays"
DEST="${1:-$HOME/.claude/skills/lastdays}"

if [ ! -f "$SRC/SKILL.md" ]; then
  echo "error: $SRC/SKILL.md not found" >&2
  exit 1
fi

mkdir -p "$(dirname "$DEST")"
ln -sfn "$SRC" "$DEST"
echo "Linked: $DEST -> $SRC"
echo "Verify: python3 \"$SRC/scripts/lastdays.py\" --diagnose"
echo "Try:    /lastdays Claude Code 7   (inside Claude Code)"
