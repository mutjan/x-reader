#!/bin/bash
# Sync dev code/pages to deploy directory, preserving deploy data and git state.
# Usage: ./deploy.sh [--dry-run] [--delete-stale] [--force]

set -euo pipefail

DEV_DIR="/Users/lzw/develop/x-reader"
DEPLOY_DIR="/Users/lzw/develop/deploy/x-reader"

DRY_RUN=""
DELETE_STALE=""
FORCE=""

for arg in "$@"; do
  case "$arg" in
    --dry-run)
      DRY_RUN="--dry-run"
      echo "=== DRY RUN ==="
      ;;
    --delete-stale)
      DELETE_STALE="--delete"
      ;;
    --force)
      FORCE="1"
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      echo "Usage: ./deploy.sh [--dry-run] [--delete-stale] [--force]" >&2
      exit 2
      ;;
  esac
done

if [[ ! -d "$DEV_DIR" || ! -d "$DEPLOY_DIR" ]]; then
  echo "DEV_DIR or DEPLOY_DIR does not exist" >&2
  exit 1
fi

if [[ -z "$FORCE" ]]; then
  deploy_status="$(git -C "$DEPLOY_DIR" status --porcelain)"
  if [[ -n "$deploy_status" ]]; then
    echo "Deploy directory has uncommitted changes. Commit/stash them first, or rerun with --force." >&2
    echo "$deploy_status" >&2
    exit 1
  fi
fi

rsync -av $DELETE_STALE $DRY_RUN \
  --exclude='.git/' \
  --exclude='.planning/' \
  --exclude='.claude/' \
  --exclude='__pycache__/' \
  --exclude='.DS_Store' \
  --exclude='.cowork-temp/' \
  --exclude='.tmp/' \
  --exclude='data/' \
  --exclude='event_groups.json' \
  --exclude='event_groups.json-*.bak' \
  --exclude='news_data.json' \
  --exclude='news_data_latest.json' \
  --exclude='.processed_ids.json' \
  --exclude='.version_counter' \
  --exclude='.work_log.json' \
  --exclude='.context.json' \
  --exclude='_ai_*_result*.json' \
  --exclude='_temp_*' \
  --exclude='_event_review_result.json' \
  --exclude='logs/' \
  --exclude='*.pyc' \
  --exclude='venv/' \
  --exclude='.env' \
  --exclude='.openclaw/' \
  --exclude='.pytest_cache/' \
  --exclude='tmp/' \
  --exclude='docs/' \
  --exclude='x-reader/' \
  --exclude='upcoming_events.json' \
  "$DEV_DIR/" "$DEPLOY_DIR/"

echo "Done. Deploy dir: $DEPLOY_DIR"
git -C "$DEPLOY_DIR" status --short
