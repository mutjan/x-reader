#!/bin/bash
# x-reader 后台管理服务启动脚本

# 项目根目录
PROJECT_ROOT="/Users/lzw/Documents/LobsterAI/lzw/x-reader"
cd "$PROJECT_ROOT" || exit 1

# 激活虚拟环境（如果有）
if [ -d "venv" ]; then
    source venv/bin/activate
fi

# 启动Flask应用，使用生产模式
export FLASK_APP="src/web/app.py"
export FLASK_ENV="production"
exec python3 -m flask run --host=0.0.0.0 --port=8081 --no-debugger --no-reload
