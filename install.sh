#!/usr/bin/env bash
# Install the ResuSkill skill for Claude Code and/or Codex by symlinking (default) or copying.
#   ./install.sh            install for both
#   ./install.sh claude     Claude Code only (~/.claude/skills)
#   ./install.sh codex      Codex only (~/.codex/skills)
#   ./install.sh --copy ... copy files instead of symlinking
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skills/resuskill"
MODE=link
TARGETS=()
for arg in "$@"; do
  case "$arg" in
    --copy) MODE=copy ;;
    claude|codex) TARGETS+=("$arg") ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "Unknown argument: $arg" >&2; exit 2 ;;
  esac
done
[ ${#TARGETS[@]} -eq 0 ] && TARGETS=(claude codex)

if ! command -v python3 >/dev/null 2>&1 || ! python3 "$SRC/scripts/resuskill.py" --version; then
  echo "Install Python 3.9+ and retry. No skill was installed." >&2
  exit 1
fi

failed=0
for target in "${TARGETS[@]}"; do
  case "$target" in
    claude) dir="${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills" ;;
    codex) dir="${CODEX_HOME:-$HOME/.codex}/skills" ;;
  esac
  mkdir -p "$dir"
  dest="$dir/resuskill"
  if [ -e "$dest" ] || [ -L "$dest" ]; then
    if [ -L "$dest" ] && [ "$(readlink "$dest")" = "$SRC" ]; then
      echo "✓ $target: already linked at $dest"
      continue
    fi
    echo "✗ $target: $dest already exists; remove it first to reinstall" >&2
    failed=1
    continue
  fi
  if [ "$MODE" = copy ]; then
    python3 - "$SRC" "$dest" <<'PY'
import shutil
import sys
shutil.copytree(sys.argv[1], sys.argv[2], ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '.DS_Store'))
PY
  else
    ln -s "$SRC" "$dest"
  fi
  echo "✓ $target: installed at $dest ($MODE)"
done

echo "Restart Claude Code / Codex, then ask: \"Use resuskill to set up my profile\"."
exit "$failed"
