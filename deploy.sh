#!/bin/bash
# Sync dev code/pages to deploy directory, preserving deploy data and git state.
# Usage: ./deploy.sh [--dry-run]

set -euo pipefail

DEV_DIR="/Users/lzw/develop/x-reader"
DEPLOY_DIR="/Users/lzw/develop/deploy/x-reader"

DRY_RUN=""
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN="--dry-run" && echo "=== DRY RUN ==="

rsync -av --delete $DRY_RUN \
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
  --exclude='upcoming_events.json' \
  "$DEV_DIR/" "$DEPLOY_DIR/"

echo "Done. Deploy dir: $DEPLOY_DIR"
