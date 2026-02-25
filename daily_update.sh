#!/bin/bash
# 每日新闻摘要更新脚本
# 由 cron 定时任务调用

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 生成版本号
VERSION=$(date +'%Y.%m.%d-001')

echo "========================================"
echo "每日新闻摘要更新 - $(date)"
echo "版本: $VERSION"
echo "========================================"

# 1. 运行 Inoreader 获取脚本（如果存在）
if [ -f "/root/.openclaw/workspace/scripts/inoreader_daily_proxy.py" ]; then
    echo "[1/4] 获取 Inoreader 数据..."
    cd /root/.openclaw/workspace/scripts
    python3 inoreader_daily_proxy.py || echo "警告: Inoreader 脚本失败，使用现有数据"
    cd "$SCRIPT_DIR"
else
    echo "[1/4] 跳过 Inoreader 获取（脚本不存在）"
fi

# 2. 更新 HTML 页面
echo "[2/4] 更新 HTML 页面..."
python3 update_news.py

# 3. 更新版本号到 HTML
sed -i "s/版本: [0-9]\{4\}\.[0-9]\{2\}\.[0-9]\{2\}-[0-9]\{3\}/版本: $VERSION/g" index.html

# 4. 提交到 GitHub
echo "[3/4] 推送到 GitHub..."
git add index.html
git commit -m "[$VERSION] Update news: $(date +%Y-%m-%d)" || echo "无变更需要提交"
git push origin main || echo "推送失败，请检查网络"

# 5. 等待 GitHub Pages 部署
echo "[4/4] 等待 GitHub Pages 部署..."
sleep 10

echo ""
echo "✅ 更新完成!"
echo "版本: $VERSION"
echo "页面地址: https://mutjan.github.io/x-reader/"
echo "========================================"
