#!/usr/bin/env python3
"""
轻量Web管理界面
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from flask import Flask, render_template, jsonify, request, redirect, url_for
import json
import subprocess
from datetime import datetime
from typing import Dict, List, Any

from src.config.settings import DATA_FILE, settings
from src.utils.common import load_json, setup_logger, save_json

app = Flask(__name__)
logger = setup_logger("web_admin")

# 禁用模板缓存
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_FILE_PATH = os.path.join(ROOT_DIR, DATA_FILE)
ZEITGEIST_CONFIG_PATH = os.path.join(ROOT_DIR, 'config', 'zeitgeist.json')

@app.route('/')
@app.route('/admin')
def index():
    """管理首页"""
    # 加载最新数据（按日期分组的字典）
    news_data = load_json(DATA_FILE_PATH, {})

    # 将所有新闻展平为列表
    all_news = []
    for date_items in news_data.values():
        all_news.extend(date_items)

    # 统计信息
    total_news = len(all_news)
    today = datetime.now().strftime('%Y-%m-%d')
    today_news = [item for item in all_news if item.get('published_at', '').startswith(today)]
    today_count = len(today_news)

    # 按来源统计
    source_stats = {}
    for item in all_news:
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

    # 加载最新数据（按日期分组的字典）
    news_data = load_json(DATA_FILE_PATH, {})

    # 将所有新闻展平为列表并按时间倒序排列
    all_news = []
    for date_items in news_data.values():
        all_news.extend(date_items)

    # 按发布时间倒序排列
    all_news.sort(key=lambda x: x.get('published_at', ''), reverse=True)

    # 搜索过滤
    filtered_news = all_news
    if search:
        filtered_news = [
            item for item in all_news
            if search in item.get('title', '').lower()
            or search in item.get('summary', '').lower()
            or any(search in entity.lower() for entity in item.get('entities', []))
        ]

    # 分页
    total = len(filtered_news)
    start = (page - 1) * page_size
    end = start + page_size
    paginated_data = filtered_news[start:end]

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
                'count': sum(len(items) for items in load_json(DATA_FILE_PATH, {}).values())
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
        from src.config.settings import RSS_CONFIG, DEFAULT_BATCH_SIZE, MAX_CACHED_IDS
        config = {
            'RSS_SOURCES': list(RSS_CONFIG.values()),
            'BATCH_SIZE': DEFAULT_BATCH_SIZE,
            'CACHE_SIZE': MAX_CACHED_IDS,
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

@app.route('/api/zeitgeist', methods=['GET'])
def api_zeitgeist_list():
    """获取时代情绪热点列表"""
    try:
        data = load_json(ZEITGEIST_CONFIG_PATH, {})
        trends = data.get('trends', [])

        # 支持筛选
        status = request.args.get('status', 'active')
        if status != 'all':
            trends = [t for t in trends if t.get('status') == status]

        # 支持搜索
        search = request.args.get('search', '').lower()
        if search:
            trends = [
                t for t in trends
                if search in t.get('keyword', '').lower()
                or search in t.get('description', '').lower()
                or any(search in e.lower() for e in t.get('related_entities', []))
            ]

        # 按热度排序
        trends.sort(key=lambda x: x.get('boost_value', 0), reverse=True)

        return jsonify({
            'code': 0,
            'data': trends,
            'total': len(trends)
        })
    except Exception as e:
        logger.error(f"获取时代情绪列表失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'获取失败: {str(e)}'
        }), 500

@app.route('/api/zeitgeist/<keyword>', methods=['GET'])
def api_zeitgeist_detail(keyword):
    """获取单个时代情绪热点详情"""
    try:
        data = load_json(ZEITGEIST_CONFIG_PATH, {})
        trends = data.get('trends', [])

        trend = next((t for t in trends if t.get('keyword') == keyword), None)
        if not trend:
            return jsonify({
                'code': -1,
                'message': '热点不存在'
            }), 404

        return jsonify({
            'code': 0,
            'data': trend
        })
    except Exception as e:
        logger.error(f"获取时代情绪详情失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'获取失败: {str(e)}'
        }), 500

@app.route('/api/zeitgeist', methods=['POST'])
def api_zeitgeist_create():
    """创建新的时代情绪热点"""
    try:
        data = request.get_json()

        # 验证必填字段
        required_fields = ['keyword', 'boost_value', 'category']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'code': -1,
                    'message': f'缺少必填字段: {field}'
                }), 400

        # 加载现有数据
        config = load_json(ZEITGEIST_CONFIG_PATH, {'trends': []})
        trends = config.get('trends', [])

        # 检查是否已存在
        if any(t.get('keyword') == data['keyword'] for t in trends):
            return jsonify({
                'code': -1,
                'message': '该关键词已存在'
            }), 400

        # 设置默认值
        new_trend = {
            'keyword': data['keyword'],
            'weight': data.get('weight', 0.7),
            'category': data['category'],
            'description': data.get('description', ''),
            'start_time': data.get('start_time', datetime.now().strftime('%Y-%m-%dT00:00:00')),
            'end_time': data.get('end_time', (datetime.now().replace(month=12, day=31)).strftime('%Y-%m-%dT00:00:00')),
            'boost_value': data['boost_value'],
            'category_name': data.get('category_name'),
            'heat_score': data.get('heat_score'),
            'trend': data.get('trend', 'stable'),
            'trend_name': data.get('trend_name', '稳定'),
            'related_entities': data.get('related_entities', []),
            'status': data.get('status', 'active'),
            'mentions_count': data.get('mentions_count', 0)
        }

        trends.append(new_trend)
        config['trends'] = trends

        # 保存到文件
        save_json(config, ZEITGEIST_CONFIG_PATH)

        logger.info(f"创建时代情绪热点成功: {data['keyword']}")

        return jsonify({
            'code': 0,
            'message': '创建成功',
            'data': new_trend
        })
    except Exception as e:
        logger.error(f"创建时代情绪热点失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'创建失败: {str(e)}'
        }), 500

@app.route('/api/zeitgeist/<keyword>', methods=['PUT'])
def api_zeitgeist_update(keyword):
    """更新时代情绪热点"""
    try:
        data = request.get_json()

        # 加载现有数据
        config = load_json(ZEITGEIST_CONFIG_PATH, {'trends': []})
        trends = config.get('trends', [])

        # 查找要更新的热点
        index = next((i for i, t in enumerate(trends) if t.get('keyword') == keyword), None)
        if index is None:
            return jsonify({
                'code': -1,
                'message': '热点不存在'
            }), 404

        # 更新字段（保留原字段，只更新传入的字段）
        updated_trend = trends[index].copy()
        for key, value in data.items():
            if key != 'keyword':  # 不允许修改keyword
                updated_trend[key] = value

        trends[index] = updated_trend
        config['trends'] = trends

        # 保存到文件
        save_json(config, ZEITGEIST_CONFIG_PATH)

        logger.info(f"更新时代情绪热点成功: {keyword}")

        return jsonify({
            'code': 0,
            'message': '更新成功',
            'data': updated_trend
        })
    except Exception as e:
        logger.error(f"更新时代情绪热点失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'更新失败: {str(e)}'
        }), 500

@app.route('/api/zeitgeist/<keyword>', methods=['DELETE'])
def api_zeitgeist_delete(keyword):
    """删除时代情绪热点"""
    try:
        # 加载现有数据
        config = load_json(ZEITGEIST_CONFIG_PATH, {'trends': []})
        trends = config.get('trends', [])

        # 查找要删除的热点
        index = next((i for i, t in enumerate(trends) if t.get('keyword') == keyword), None)
        if index is None:
            return jsonify({
                'code': -1,
                'message': '热点不存在'
            }), 404

        # 删除
        deleted_trend = trends.pop(index)
        config['trends'] = trends

        # 保存到文件
        save_json(config, ZEITGEIST_CONFIG_PATH)

        logger.info(f"删除时代情绪热点成功: {keyword}")

        return jsonify({
            'code': 0,
            'message': '删除成功',
            'data': deleted_trend
        })
    except Exception as e:
        logger.error(f"删除时代情绪热点失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'删除失败: {str(e)}'
        }), 500

@app.route('/api/zeitgeist/test', methods=['POST'])
def api_zeitgeist_test():
    """测试内容匹配"""
    try:
        from src.processors.zeitgeist import zeitgeist_manager

        data = request.get_json()
        title = data.get('title', '')
        entities = data.get('entities', [])
        content = data.get('content', '')

        # 执行匹配
        total_boost, matched_trends = zeitgeist_manager.get_boost_for_content(title, content, entities)

        return jsonify({
            'code': 0,
            'data': {
                'matched_trends': matched_trends,
                'total_boost': total_boost
            }
        })
    except Exception as e:
        logger.error(f"测试时代情绪匹配失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'测试失败: {str(e)}'
        }), 500

if __name__ == '__main__':
    # 创建模板目录
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(template_dir, exist_ok=True)

    # 启动服务（生产环境关闭debug模式）
    app.run(host='0.0.0.0', port=8081, debug=False, use_reloader=False)
