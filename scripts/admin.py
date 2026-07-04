#!/usr/bin/env python3
"""
启动Web管理后台
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.web.app import app

if __name__ == '__main__':
    print("🚀 启动 X-Reader 管理后台...")
    print("📡 访问地址: http://localhost:8753")
    print("🔑 管理后台功能: 查看新闻、手动触发同步、查看系统状态")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8753, debug=False)
