#!/bin/bash
# 部署脚本：同步代码和页面到部署目录（保留目标端数据不动）
# 用法: ./scripts/deploy.sh [--dry-run]

SRC="/Users/lzw/develop/x-reader"
DST="/Users/lzw/develop/deploy/x-reader"

# 排除列表（--delete 不加 --delete-excluded，所以排除项在目标端不受影响）
EXCLUDES=(
    # 数据和临时
    --exclude="data/"
    --exclude=".tmp/"
    --exclude="tmp/"
    --exclude="logs/"
    --exclude="__pycache__/"
    --exclude="*.pyc"
    --exclude="*.log"
    --exclude="*.bak"
    # Git 和开发工具
    --exclude=".git/"
    --exclude=".claude/"
    --exclude=".cowork-temp/"
    --exclude=".openclaw/"
    --exclude=".planning/"
    --exclude=".pytest_cache/"
    --exclude="docs/"
    --exclude="venv/"
    # 根目录状态文件
    --exclude=".processed_ids.json"
    --exclude=".work_log.json"
    --exclude=".version_counter"
    --exclude=".env"
    --exclude=".DS_Store"
    # 根目录临时/结果文件
    --exclude="_ai_*"
    --exclude="_temp_*"
    --exclude="full_ai_*"
    --exclude="news_data*.json"
    --exclude="event_groups.json"
    --exclude="upcoming_events.json"
    --exclude="_ai_scoring_result.json"
    # AI Agent 配置文件
    --exclude="AGENTS.md"
    --exclude="HEARTBEAT.md"
    --exclude="IDENTITY.md"
    --exclude="SOUL.md"
    --exclude="TOOLS.md"
    --exclude="USER.md"
)

RSYNC_OPTS=(-av --delete "${EXCLUDES[@]}")

if [ "$1" = "--dry-run" ]; then
    echo "=== DRY RUN ==="
    RSYNC_OPTS+=(-n)
fi

echo "部署 $SRC -> $DST"
rsync "${RSYNC_OPTS[@]}" "$SRC/" "$DST/"

# config/ 下的 json 被上方 news_data*.json 排除规则误杀，单独同步
rsync -av "$SRC/config/" "$DST/config/"

echo ""
echo "部署完成！目标目录: $DST"
