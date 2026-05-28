#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$ROOT_DIR/skills"
DEST="${CODEX_HOME:-$HOME/.codex}/skills"
DRY_RUN=0
LIST_ONLY=0
SELECTED=()

usage() {
  cat <<'EOF'
Usage: ./skills.sh [options]

Local Codex-style installer for this repository's skills.
For Claude Code, Codex, Cursor, and other multi-agent installs, prefer:
  npx skills add santialferez/dictat-generator-skill --skill gemini-dictat-generator -a claude-code -a codex
For Pi Coding Agent, prefer:
  pi install git:github.com/santialferez/dictat-generator-skill

Options:
  --dest PATH       Install destination. Default: ~/.codex/skills or $CODEX_HOME/skills
  --skill NAME      Install only one skill. May be repeated.
  --list            List available skills.
  --dry-run         Print actions without copying.
  -h, --help        Show this help.
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dest)
      DEST="$2"
      shift 2
      ;;
    --skill)
      SELECTED+=("$2")
      shift 2
      ;;
    --list)
      LIST_ONLY=1
      shift
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$SKILLS_DIR" ]]; then
  echo "No skills directory found at $SKILLS_DIR" >&2
  exit 1
fi

available_skills=()
for skill_path in "$SKILLS_DIR"/*; do
  [[ -d "$skill_path" && -f "$skill_path/SKILL.md" ]] || continue
  available_skills+=("$(basename "$skill_path")")
done

if [[ "$LIST_ONLY" -eq 1 ]]; then
  printf '%s\n' "${available_skills[@]}"
  exit 0
fi

if [[ "${#SELECTED[@]}" -eq 0 ]]; then
  SELECTED=("${available_skills[@]}")
fi

for skill in "${SELECTED[@]}"; do
  src="$SKILLS_DIR/$skill"
  dst="$DEST/$skill"
  if [[ ! -f "$src/SKILL.md" ]]; then
    echo "Skill not found: $skill" >&2
    exit 1
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "Would install $src -> $dst"
    continue
  fi
  mkdir -p "$DEST"
  rm -rf "$dst"
  cp -R "$src" "$dst"
  echo "Installed $skill -> $dst"
done
