#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'USAGE'
Usage: require_clean_git.sh [repo_path]

Environment variables:
  REQUIRE_CLEAN_ALLOW_DIRTY   Set to 1 to bypass this guard (default: 0)
USAGE
}

if [[ $# -gt 1 ]]; then
  usage
  exit 1
fi

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "${REQUIRE_CLEAN_ALLOW_DIRTY:-0}" == "1" ]]; then
  echo "require_clean_git: bypassed via REQUIRE_CLEAN_ALLOW_DIRTY=1"
  exit 0
fi

REPO_PATH="${1:-.}"

if ! git -C "${REPO_PATH}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not a git repository: ${REPO_PATH}" >&2
  exit 2
fi

STATUS="$(git -C "${REPO_PATH}" status --porcelain)"
if [[ -n "${STATUS}" ]]; then
  echo "ERROR: git tree is not clean in ${REPO_PATH}" >&2
  git -C "${REPO_PATH}" status --short >&2
  echo >&2
  echo "Deploy/test determinism requires a clean tree." >&2
  exit 2
fi

echo "require_clean_git: clean (${REPO_PATH})"
