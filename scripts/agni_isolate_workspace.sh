#!/usr/bin/env bash
set -euo pipefail

# Snapshot dirty/untracked AGNI repo state into a local-only WIP branch,
# then return the deploy branch to a clean state.

usage() {
  cat <<'USAGE'
Usage: agni_isolate_workspace.sh [--apply]

Environment variables:
  AGNI_SSH_TARGET         SSH host/alias (default: agni)
  AGNI_REPO_PATH          Remote repo path (default: /home/openclaw/repos/saraswati-dharmic-agora)
  AGNI_DEPLOY_BRANCH      Branch to return to for deploys (default: main)
  AGNI_WIP_PREFIX         Prefix for local WIP branch (default: agni/local-wip)
USAGE
}

APPLY=0
if [[ $# -gt 1 ]]; then
  usage
  exit 1
fi
if [[ $# -eq 1 ]]; then
  case "$1" in
    --apply) APPLY=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; usage; exit 1 ;;
  esac
fi

AGNI_SSH_TARGET="${AGNI_SSH_TARGET:-agni}"
AGNI_REPO_PATH="${AGNI_REPO_PATH:-/home/openclaw/repos/saraswati-dharmic-agora}"
AGNI_DEPLOY_BRANCH="${AGNI_DEPLOY_BRANCH:-main}"
AGNI_WIP_PREFIX="${AGNI_WIP_PREFIX:-agni/local-wip}"

echo "== AGNI Workspace Isolation =="
echo "ssh_target=${AGNI_SSH_TARGET}"
echo "repo_path=${AGNI_REPO_PATH}"
echo "deploy_branch=${AGNI_DEPLOY_BRANCH}"
echo "apply=${APPLY}"
echo

ssh "${AGNI_SSH_TARGET}" bash -s -- \
  "${AGNI_REPO_PATH}" \
  "${AGNI_DEPLOY_BRANCH}" \
  "${AGNI_WIP_PREFIX}" \
  "${APPLY}" <<'REMOTE'
set -euo pipefail

REPO_PATH="$1"
DEPLOY_BRANCH="$2"
WIP_PREFIX="$3"
APPLY="$4"

cd "${REPO_PATH}"

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "ERROR: not a git repo at ${REPO_PATH}" >&2
  exit 2
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD)"
echo "current_branch=${CURRENT_BRANCH}"
echo "-- current status --"
git status --short

if [[ -z "$(git status --porcelain)" ]]; then
  echo "repo already clean; no isolation needed"
  exit 0
fi

TS="$(date -u +%Y%m%d_%H%M%SZ)"
WIP_BRANCH="${WIP_PREFIX}-${TS}"
echo "planned_wip_branch=${WIP_BRANCH}"

if [[ "${APPLY}" != "1" ]]; then
  echo "dry_run=1"
  echo "run with --apply to snapshot and clean deploy branch"
  exit 0
fi

git switch -c "${WIP_BRANCH}"
git add -A

if git diff --cached --quiet; then
  echo "no_staged_changes_after_add=1"
else
  git commit -m "chore(agni): snapshot local workspace ${TS}"
fi

git switch "${DEPLOY_BRANCH}"

if [[ -n "$(git status --porcelain)" ]]; then
  echo "ERROR: deploy branch still dirty after isolation" >&2
  git status --short >&2
  exit 3
fi

echo "isolation_complete=1"
echo "wip_branch=${WIP_BRANCH}"
echo "deploy_branch_clean=${DEPLOY_BRANCH}"
REMOTE
