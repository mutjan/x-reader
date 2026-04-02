#!/usr/bin/env python3
"""
轻量Web管理界面
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from flask import Flask, render_template, jsonify, request, redirect, url_for, session
from functools import wraps
import json
import subprocess
from datetime import datetime
from typing import Dict, List, Any

from src.config.settings import DATA_FILE, settings, EVENT_GROUPS_FILE
from src.utils.common import load_json, setup_logger, save_json
from src.data.feedback_store import FeedbackStore
from src.data.source_store import source_store

app = Flask(__name__)
logger = setup_logger("web_admin")

# 配置Flask session
app.config['SECRET_KEY'] = settings.SECRET_KEY
app.config['PERMANENT_SESSION_LIFETIME'] = 24 * 60 * 60  # 24小时有效期

# 禁用模板缓存
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

# 登录校验装饰器
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'logged_in' not in session:
            # API请求返回401，页面请求跳转到登录页
            if request.path.startswith('/api/'):
                return jsonify({'code': -1, 'message': '未登录，请先登录'}), 401
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# 项目根目录
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DATA_FILE_PATH = os.path.join(ROOT_DIR, DATA_FILE)
EVENT_GROUPS_FILE_PATH = os.path.join(ROOT_DIR, EVENT_GROUPS_FILE)
ZEITGEIST_CONFIG_PATH = os.path.join(ROOT_DIR, 'config', 'zeitgeist.json')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'POST':
        password = request.form.get('password', '')
        if password == settings.ADMIN_PASSWORD:
            session['logged_in'] = True
            session.permanent = True
            return redirect(url_for('index'))
        return render_template('login.html', error='密码错误，请重试')

    # 已登录用户直接跳转到首页
    if 'logged_in' in session:
        return redirect(url_for('index'))

    return render_template('login.html')

@app.route('/logout')
def logout():
    """登出"""
    session.pop('logged_in', None)
    return redirect(url_for('login'))

@app.route('/')
@app.route('/admin')
@login_required
def index():
    """管理首页"""
    # 加载最新数据（按日期分组的字典）
    data = load_json(DATA_FILE_PATH, {})
    news_data = data.get('news', {})  # 新结构中news字段存储日期分组

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
@login_required
def api_news():
    """获取新闻数据API"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    search = request.args.get('search', '').lower()
    filter_param = request.args.get('filter', '')
    sort_param = request.args.get('sort', 'published_at:desc')

    # 加载最新数据（按日期分组的字典）
    data = load_json(DATA_FILE_PATH, {})
    news_data = data.get('news', {})  # 新结构中news字段存储日期分组

    # 将所有新闻展平为列表
    all_news = []
    for date_items in news_data.values():
        all_news.extend(date_items)

    # 搜索过滤
    filtered_news = all_news
    if search:
        filtered_news = [
            item for item in filtered_news
            if search in item.get('title', '').lower()
            or search in item.get('summary', '').lower()
            or any(search in entity.lower() for entity in item.get('entities', []))
        ]

    # 条件筛选
    if filter_param:
        try:
            import json
            filters = json.loads(filter_param)

            # 领域筛选
            if 'domain' in filters and filters['domain']:
                filtered_news = [item for item in filtered_news if item.get('type', '') == filters['domain']]

            # 热度筛选
            if 'score_min' in filters and filters['score_min'] is not None:
                filtered_news = [item for item in filtered_news if item.get('score', 0) >= filters['score_min']]
            if 'score_max' in filters and filters['score_max'] is not None:
                filtered_news = [item for item in filtered_news if item.get('score', 0) <= filters['score_max']]

            # 时间筛选
            if 'start_time' in filters and filters['start_time']:
                filtered_news = [item for item in filtered_news if item.get('published_at', '') >= filters['start_time']]
            if 'end_time' in filters and filters['end_time']:
                filtered_news = [item for item in filtered_news if item.get('published_at', '') <= filters['end_time']]

            # 评级筛选
            if 'ratings' in filters and filters['ratings']:
                filtered_news = [item for item in filtered_news if item.get('rating', '') in filters['ratings']]
        except Exception as e:
            logger.error(f"筛选参数解析失败: {e}")

    # 排序
    sort_field, sort_order = sort_param.split(':') if ':' in sort_param else ('published_at', 'desc')
    reverse = sort_order == 'desc'

    if sort_field == 'score':
        filtered_news.sort(key=lambda x: x.get('score', 0), reverse=reverse)
    elif sort_field == 'published_at':
        filtered_news.sort(key=lambda x: x.get('published_at', ''), reverse=reverse)
    elif sort_field == 'sources_count':
        filtered_news.sort(key=lambda x: x.get('sources', 0), reverse=reverse)
    else:
        # 默认按时间倒序
        filtered_news.sort(key=lambda x: x.get('published_at', ''), reverse=True)

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
@login_required
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
@login_required
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
                'count': sum(len(items) for items in load_json(DATA_FILE_PATH, {}).get('news', {}).values())
            },
            'github': {
                'enabled': bool(settings.GITHUB_TOKEN),
                'branch': settings.GITHUB_BRANCH
            }
        }
    })

@app.route('/api/config', methods=['GET', 'POST'])
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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
@login_required
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

@app.route('/api/feedback', methods=['POST'])
@login_required
def api_submit_feedback():
    """提交评分反馈"""
    try:
        data = request.get_json()
        # 验证必填字段
        required_fields = ['news_id', 'original_grade', 'original_score', 'corrected_grade', 'corrected_score']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'code': -1,
                    'message': f'缺少必填字段: {field}'
                }), 400
        # 验证分级格式
        valid_grades = ['S', 'A+', 'A', 'B', 'C']
        if data['corrected_grade'] not in valid_grades:
            return jsonify({
                'code': -1,
                'message': f'无效的分级: {data["corrected_grade"]}，必须是S/A+/A/B/C之一'
            }), 400
        # 验证分数范围
        corrected_score = int(data['corrected_score'])
        if corrected_score < 0 or corrected_score > 100:
            return jsonify({
                'code': -1,
                'message': '分数必须在0-100之间'
            }), 400
        # 存储反馈
        feedback_store = FeedbackStore()
        success = feedback_store.add_feedback(
            news_id=data['news_id'],
            original_grade=data['original_grade'],
            original_score=int(data['original_score']),
            corrected_grade=data['corrected_grade'],
            corrected_score=corrected_score,
            reason=data.get('reason', ''),
            entities=data.get('entities', [])
        )
        if success:
            return jsonify({
                'code': 0,
                'message': '反馈提交成功'
            })
        else:
            return jsonify({
                'code': -1,
                'message': '反馈提交失败，请稍后重试'
            }), 500
    except Exception as e:
        logger.error(f"提交反馈失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'提交失败: {str(e)}'
        }), 500

# 源管理API
@app.route('/api/sources', methods=['GET'])
@login_required
def api_sources_list():
    """获取源列表"""
    try:
        include_disabled = request.args.get('include_disabled', 'false').lower() == 'true'
        sources = source_store.get_all_sources(include_disabled=include_disabled)
        return jsonify({
            'code': 0,
            'data': sources,
            'total': len(sources)
        })
    except Exception as e:
        logger.error(f"获取源列表失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'获取失败: {str(e)}'
        }), 500

@app.route('/api/sources', methods=['POST'])
@login_required
def api_sources_create():
    """创建新源"""
    try:
        data = request.get_json()

        # 验证必填字段
        required_fields = ['name', 'url', 'type']
        for field in required_fields:
            if field not in data:
                return jsonify({
                    'code': -1,
                    'message': f'缺少必填字段: {field}'
                }), 400

        # 验证源类型
        valid_types = ['rss', 'api', 'twitter', 'inoreader']
        if data['type'] not in valid_types:
            return jsonify({
                'code': -1,
                'message': f'无效的源类型: {data["type"]}，必须是rss/api/twitter/inoreader之一'
            }), 400

        # 创建源
        new_source = source_store.add_source(
            name=data['name'],
            url=data['url'],
            source_type=data['type'],
            enabled=data.get('enabled', True),
            weight=data.get('weight', 1.0),
            config=data.get('config', {})
        )

        if new_source:
            return jsonify({
                'code': 0,
                'message': '创建成功',
                'data': new_source
            })
        else:
            return jsonify({
                'code': -1,
                'message': '创建失败，请稍后重试'
            }), 500

    except Exception as e:
        logger.error(f"创建源失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'创建失败: {str(e)}'
        }), 500

@app.route('/api/sources/<source_id>', methods=['PUT'])
@login_required
def api_sources_update(source_id):
    """更新源"""
    try:
        data = request.get_json()

        # 验证源存在
        existing_source = source_store.get_source(source_id)
        if not existing_source:
            return jsonify({
                'code': -1,
                'message': '源不存在'
            }), 404

        # 更新字段
        update_data = {}
        allowed_fields = ['name', 'url', 'type', 'enabled', 'weight', 'config']
        for key, value in data.items():
            if key in allowed_fields:
                update_data[key] = value

        updated_source = source_store.update_source(source_id, **update_data)

        if updated_source:
            return jsonify({
                'code': 0,
                'message': '更新成功',
                'data': updated_source
            })
        else:
            return jsonify({
                'code': -1,
                'message': '更新失败，请稍后重试'
            }), 500

    except Exception as e:
        logger.error(f"更新源失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'更新失败: {str(e)}'
        }), 500

@app.route('/api/sources/<source_id>', methods=['DELETE'])
@login_required
def api_sources_delete(source_id):
    """删除源"""
    try:
        success = source_store.delete_source(source_id)
        if success:
            return jsonify({
                'code': 0,
                'message': '删除成功'
            })
        else:
            return jsonify({
                'code': -1,
                'message': '删除失败，源不存在'
            }), 404
    except Exception as e:
        logger.error(f"删除源失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'删除失败: {str(e)}'
        }), 500

@app.route('/api/events')
@login_required
def api_events():
    """获取事件分组数据API"""
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 10))
    search = request.args.get('search', '').lower()
    filter_param = request.args.get('filter', '')
    sort_param = request.args.get('sort', 'max_score:desc')

    try:
        # 加载事件分组和新闻数据
        event_groups = load_json(EVENT_GROUPS_FILE_PATH, [])
        news_data = load_json(DATA_FILE_PATH, {}).get('news', {})

        # 创建新闻查找字典（ID到新闻对象的映射）
        news_lookup = {}
        for date_items in news_data.values():
            for news in date_items:
                news_lookup[news['id']] = news

        # 处理事件分组，关联新闻数据
        processed_events = []
        for group in event_groups:
            # 获取该事件的所有新闻
            event_news = []
            for news_id in group.get('news_ids', []):
                if news_id in news_lookup:
                    event_news.append(news_lookup[news_id])

            # 跳过没有有效新闻的事件
            if not event_news:
                logger.debug(f"跳过事件 {group.get('group_id')}，没有有效新闻")
                continue

            # 构建事件对象
            event = {
                'event_id': group.get('group_id', group.get('event_id', '')),
                'title': group.get('event_title', group.get('title', '未命名事件')),
                'max_grade': group.get('max_grade', 'B'),
                'max_score': group.get('max_score', 0),
                'start_time': group.get('first_seen_at', group.get('start_time', '')),
                'end_time': group.get('last_seen_at', group.get('end_time', '')),
                'news_count': len(event_news),
                'entities': group.get('entities', []),
                'news_list': event_news
            }

            processed_events.append(event)

        # 搜索过滤
        filtered_events = processed_events
        if search:
            filtered_events = [
                event for event in filtered_events
                if search in event['title'].lower()
                or any(search in entity.lower() for entity in event['entities'])
                or any(search in news.get('title', '').lower() for news in event['news_list'])
                or any(search in news.get('summary', '').lower() for news in event['news_list'])
            ]

        # 条件筛选（应用到嵌套的新闻项）
        if filter_param:
            try:
                filters = json.loads(filter_param)
                temp_events = []

                for event in filtered_events:
                    # 对事件内的新闻应用筛选
                    filtered_news = event['news_list'].copy()

                    # 领域筛选
                    if 'domain' in filters and filters['domain']:
                        filtered_news = [n for n in filtered_news if n.get('type', '') == filters['domain']]

                    # 热度筛选
                    if 'score_min' in filters and filters['score_min'] is not None:
                        filtered_news = [n for n in filtered_news if n.get('score', 0) >= filters['score_min']]
                    if 'score_max' in filters and filters['score_max'] is not None:
                        filtered_news = [n for n in filtered_news if n.get('score', 0) <= filters['score_max']]

                    # 时间筛选
                    if 'start_time' in filters and filters['start_time']:
                        filtered_news = [n for n in filtered_news if n.get('published_at', '') >= filters['start_time']]
                    if 'end_time' in filters and filters['end_time']:
                        filtered_news = [n for n in filtered_news if n.get('published_at', '') <= filters['end_time']]

                    # 评级筛选
                    if 'ratings' in filters and filters['ratings']:
                        filtered_news = [n for n in filtered_news if n.get('rating', '') in filters['ratings']]

                    # 如果筛选后还有新闻，保留事件并更新新闻列表
                    if filtered_news:
                        updated_event = event.copy()
                        updated_event['news_list'] = filtered_news
                        updated_event['news_count'] = len(filtered_news)
                        # 重新计算事件的max_score和max_grade
                        if filtered_news:
                            updated_event['max_score'] = max(n.get('score', 0) for n in filtered_news)
                            grade_order = {"S": 5, "A+": 4, "A": 3, "B": 2, "C": 1}
                            updated_event['max_grade'] = max(
                                (n.get('grade', 'B') for n in filtered_news),
                                key=lambda g: grade_order.get(g, 0)
                            )
                        temp_events.append(updated_event)

                filtered_events = temp_events

            except Exception as e:
                logger.error(f"事件筛选参数解析失败: {e}")

        # 排序
        sort_field, sort_order = sort_param.split(':') if ':' in sort_param else ('max_score', 'desc')
        reverse = sort_order == 'desc'

        if sort_field == 'max_score':
            filtered_events.sort(key=lambda x: x.get('max_score', 0), reverse=reverse)
        elif sort_field == 'news_count':
            filtered_events.sort(key=lambda x: x.get('news_count', 0), reverse=reverse)
        elif sort_field == 'start_time':
            filtered_events.sort(key=lambda x: x.get('start_time', ''), reverse=reverse)
        elif sort_field == 'end_time':
            filtered_events.sort(key=lambda x: x.get('end_time', ''), reverse=reverse)
        else:
            # 默认按最高评分倒序
            filtered_events.sort(key=lambda x: x.get('max_score', 0), reverse=True)

        # 分页
        total = len(filtered_events)
        start = (page - 1) * page_size
        end = start + page_size
        paginated_data = filtered_events[start:end]

        return jsonify({
            'code': 0,
            'data': paginated_data,
            'total': total,
            'page': page,
            'page_size': page_size
        })

    except Exception as e:
        logger.error(f"获取事件数据失败: {e}")
        return jsonify({
            'code': -1,
            'message': f'获取事件数据失败: {str(e)}'
        }), 500

if __name__ == '__main__':
    # 创建模板目录
    template_dir = os.path.join(os.path.dirname(__file__), 'templates')
    os.makedirs(template_dir, exist_ok=True)

    # 启动服务（临时开启debug模式获取错误信息）
    app.run(host='0.0.0.0', port=8081, debug=True, use_reloader=False)
