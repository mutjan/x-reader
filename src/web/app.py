#!/usr/bin/env python3
"""
轻量Web管理界面
"""
from flask import Flask, render_template, jsonify, request, redirect, url_for
import json
import os
import subprocess
from datetime import datetime
from typing import Dict, List, Any

from src.config.settings import DATA_FILE, settings
from src.utils.common import load_json, setup_logger

app = Flask(__name__)
logger = setup_logger("web_admin")

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_FILE_PATH = os.path.join(ROOT_DIR, DATA_FILE)

@app.route('/')
def index():
    """管理首页"""
    # 加载最新数据
    news_data = load_json(DATA_FILE_PATH, [])

    # 统计信息
    total_news = len(news_data)
    today = datetime.now().strftime('%Y-%m-%d')
    today_news = [item for item in news_data if item.get('published_at', '').startswith(today)]
    today_count = len(today_news)

    # 按来源统计
    source_stats = {}
    for item in news_data:
        for source in item.get('sourceLinks', []):
            source_name = source.get('name', '未知')
            source_stats[source_name] = source_stats.get(source_name, 0) + 1

    top_sources = sorted(source_stats.items(), key=lambda x: x[1], reverse=True)[:5]

    # 最近更新时间
    last_update = datetime.fromtimestamp(os.path.getmtime(DATA_FILE_PATH)).strftime('%Y-%m-%d %H:%M:%S') if os.path.exists(DATA_FILE_PATH) else '从未'

    return render_template('admin.html',
                         total_news=total_news,
                         today_count=today_count,
                         last_update=last_update,
                         top_sources=top_sources)

@app.route('/api/news')
def api_news():
    """获取新闻数据API"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    search = request.args.get('search', '').lower()

    news_data = load_json(DATA_FILE_PATH, [])

    # 搜索过滤
    if search:
        news_data = [
            item for item in news_data
            if search in item.get('title', '').lower()
            or search in item.get('summary', '').lower()
            or any(search in entity.lower() for entity in item.get('entities', []))
        ]

    # 分页
    total = len(news_data)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_data = news_data[start:end]

    return jsonify({
        'code': 0,
        'data': paginated_data,
        'total': total,
        'page': page,
        'page_size': page_size
    })

@app.route('/api/trigger-sync', methods=['POST'])
def api_trigger_sync():
    """手动触发同步任务"""
    try:
        # 执行同步脚本
        result = subprocess.run(
            ['python', os.path.join(ROOT_DIR, 'main.py')],
            capture_output=True,
            text=True,
            timeout=300  # 5分钟超时
        )

        if result.returncode == 0:
            return jsonify({
                'code': 0,
                'message': '同步成功',
                'output': result.stdout
            })
        else:
            return jsonify({
                'code': -1,
                'message': f'同步失败: {result.stderr}',
                'output': result.stdout
            })
    except Exception as e:
        logger.error(f"触发同步失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'触发同步失败: {str(e)}'
        }), 500

@app.route('/api/status')
def api_status():
    """系统状态API"""
    # 磁盘使用情况
    disk = os.statvfs(ROOT_DIR)
    disk_total = disk.f_frsize * disk.f_blocks / 1024 / 1024 / 1024
    disk_free = disk.f_frsize * disk.f_bfree / 1024 / 1024 / 1024
    disk_used = disk_total - disk_free

    # 数据文件大小
    data_size = os.path.getsize(DATA_FILE_PATH) / 1024 / 1024 if os.path.exists(DATA_FILE_PATH) else 0

    # 最后更新时间
    last_update = datetime.fromtimestamp(os.path.getmtime(DATA_FILE_PATH)).strftime('%Y-%m-%d %H:%M:%S') if os.path.exists(DATA_FILE_PATH) else '从未'

    return jsonify({
        'code': 0,
        'data': {
            'disk': {
                'total': round(disk_total, 2),
                'used': round(disk_used, 2),
                'free': round(disk_free, 2),
                'usage': round(disk_used / disk_total * 100, 1) if disk_total > 0 else 0
            },
            'data': {
                'size': round(data_size, 2),
                'last_update': last_update,
                'count': len(load_json(DATA_FILE_PATH, []))
            },
            'github': {
                'enabled': bool(settings.GITHUB_TOKEN),
                'branch': settings.GITHUB_BRANCH
            }
        }
    })

@app.route('/api/config', methods=['GET', 'POST'])
def api_config():
    """配置管理API"""
    if request.method == 'GET':
        # 返回当前配置（脱敏处理）
        config = {
            'RSS_SOURCES': settings.RSS_SOURCES,
            'BATCH_SIZE': settings.BATCH_SIZE,
            'CACHE_SIZE': settings.CACHE_SIZE,
            'GITHUB_BRANCH': settings.GITHUB_BRANCH,
            'GITHUB_TOKEN_SET': bool(settings.GITHUB_TOKEN)
        }
        return jsonify({
            'code': 0,
            'data': config
        })
    else:
        # 更新配置（仅支持部分参数）
        data = request.get_json()
        # 这里可以实现配置更新逻辑，写入到.env文件
        return jsonify({
            'code': 0,
            'message': '配置更新成功（功能开发中）'
        })

if __name__ == '__main__':
    # 创建模板目录
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(template_dir, exist_ok=True)

    # 启动服务
    app.run(host='0.0.0.0', port=8080, debug=True)
