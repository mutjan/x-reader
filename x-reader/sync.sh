#!/bin/bash
# x-reader 同步脚本
# 用于定时调度执行新闻同步任务

# 进入项目根目录
cd "$(dirname "$0")"

# 创建日志目录
mkdir -p logs

# 日志文件路径
LOG_FILE="logs/sync_$(date +%Y%m%d_%H%M%S).log"

# 执行同步
echo "[$(date +'%Y-%m-%d %H:%M:%S')] 开始同步新闻..." | tee -a "$LOG_FILE"

# 默认增量更新（最近2小时）
python main.py "$@" >> "$LOG_FILE" 2>&1
EXIT_CODE=$?

if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] 同步成功！" | tee -a "$LOG_FILE"
else
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] 同步失败，退出码: $EXIT_CODE" | tee -a "$LOG_FILE"
fi

# 清理7天前的日志
find logs -name "sync_*.log" -mtime +7 -delete

exit $EXIT_CODE
