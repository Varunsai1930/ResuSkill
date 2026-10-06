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

if ! command -v python3 >/dev/null 2>&1; then
  echo "Warning: python3 not found. ResuSkill needs Python 3.9+." >&2
fi

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
    continue
  fi
  if [ "$MODE" = copy ]; then
    cp -R "$SRC" "$dest"
  else
    ln -s "$SRC" "$dest"
  fi
  echo "✓ $target: installed at $dest ($MODE)"
done

python3 "$SRC/scripts/resuskill.py" --version >/dev/null 2>&1 && echo "✓ CLI runs: $(python3 "$SRC/scripts/resuskill.py" --version)"
echo "Restart Claude Code / Codex, then ask: \"Use resuskill to set up my profile\"."
