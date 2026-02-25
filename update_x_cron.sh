#!/bin/bash
# X帖子每小时更新 - 直接执行版本
# 由 cron 调用，不经过子agent

set -e

cd /root/.openclaw/workspace/x_reader

echo "========================================"
echo "X RSS 更新任务 - $(date)"
echo "========================================"

# 运行Python脚本
python3 update_x_posts.py > /tmp/x_update.log 2>&1
EXIT_CODE=$?

# 发送结果到Feishu（可选）
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ X帖子更新成功"
    cat /tmp/x_update.log
else
    echo "❌ X帖子更新失败"
    cat /tmp/x_update.log
fi

exit $EXIT_CODE
