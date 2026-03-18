#!/usr/bin/env python3
"""
获取 X RSS 并聚合事件、生成中文摘要
每小时执行一次，保留当天之前的内容
"""

import json
import base64
import requests
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from urllib.parse import urlparse
import hashlib

# 配置
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = "mutjan/x-reader"
FILE_PATH = "index.html"
LOCAL_FILE = "/root/.openclaw/workspace/x_reader/index.html"
RSS_URL = "https://rss.app/feeds/WP7twJCBciyJES4y.xml"

def get_file_sha():
    """获取文件的当前 SHA"""
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    response = requests.get(url, headers=headers, timeout=30)
    if response.status_code == 200:
        return response.json().get('sha'), response.json().get('content')
    return None, None

def get_current_archive():
    """从当前页面获取 X_EVENTS_ARCHIVE 数据"""
    sha, content_b64 = get_file_sha()
    if not content_b64:
        return {}
    
    try:
        content = base64.b64decode(content_b64).decode('utf-8')
        # 提取 X_EVENTS_ARCHIVE
        match = re.search(r'const X_EVENTS_ARCHIVE = \{([\s\S]*?)\};', content)
        if match:
            archive_str = '{' + match.group(1) + '}'
            return json.loads(archive_str)
    except Exception as e:
        print(f"解析现有数据出错: {e}")
    
    return {}

def fetch_rss():
    """获取 RSS 内容"""
    try:
        response = requests.get(RSS_URL, timeout=30)
        response.raise_for_status()
        
        # 解析 XML
        root = ET.fromstring(response.content)
        
        # RSS 2.0 格式
        items = []
        for item in root.findall('.//item'):
            title = item.find('title')
            link = item.find('link')
            description = item.find('description')
            pub_date = item.find('pubDate')
            
            # 尝试获取作者
            author = item.find('.//{http://purl.org/dc/elements/1.1/}creator')
            if author is None:
                author = item.find('author')
            
            # 处理标题 - 提取转帖的原始内容
            raw_title = title.text if title is not None else ''
            processed_title = extract_original_content(raw_title)
            
            items.append({
                'title': processed_title,
                'raw_title': raw_title,
                'url': link.text if link is not None else '',
                'content': description.text if description is not None else '',
                'author': author.text if author is not None else 'Unknown',
                'time': pub_date.text if pub_date is not None else ''
            })
        
        return items
    except Exception as e:
        print(f"获取 RSS 失败: {e}")
        return []

def extract_original_content(text):
    """提取转帖中的原始内容，去掉RT前缀"""
    if not text:
        return text
    
    # 匹配 "RT @username: " 或 "RT @username " 前缀
    import re
    
    # 处理 "RT @username: content" 格式
    rt_pattern = r'^RT\s+@\w+:\s*'
    match = re.match(rt_pattern, text)
    if match:
        return text[match.end():].strip()
    
    # 处理 "RT @username content" 格式（没有冒号）
    rt_pattern2 = r'^RT\s+@\w+\s+'
    match = re.match(rt_pattern2, text)
    if match:
        return text[match.end():].strip()
    
    return text

def extract_keywords(text):
    """提取关键词用于事件聚类"""
    # 常见科技关键词
    tech_keywords = [
        'AI', 'OpenAI', 'ChatGPT', 'GPT', 'Claude', 'Anthropic', 'LLM', '大模型',
        'Meta', 'Facebook', 'Instagram', 'WhatsApp',
        'Google', 'Alphabet', 'Gemini', 'Bard',
        'Apple', 'iPhone', 'iPad', 'Mac', 'Vision Pro',
        'Microsoft', 'Azure', 'Copilot', 'Windows',
        'Amazon', 'AWS', 'Alexa',
        'Nvidia', 'GPU', 'CUDA', 'RTX',
        'AMD', 'Intel', 'TSMC',
        'Tesla', 'SpaceX', 'Starlink', 'Elon',
        'Bitcoin', 'Crypto', 'Blockchain', 'Web3',
        'startup', 'funding', 'IPO', 'acquisition',
        'layoff', 'hiring', 'remote work'
    ]
    
    text_lower = text.lower()
    found_keywords = []
    
    for kw in tech_keywords:
        if kw.lower() in text_lower:
            found_keywords.append(kw)
    
    return found_keywords

def cluster_posts(posts):
    """将帖子按话题聚类"""
    clusters = {}
    
    for post in posts:
        content = f"{post.get('title', '')} {post.get('content', '')}"
        keywords = extract_keywords(content)
        
        # 使用关键词组合作为聚类键
        if keywords:
            cluster_key = tuple(sorted(keywords[:3]))  # 最多取3个关键词
        else:
            # 无关键词时按作者聚类
            cluster_key = (post.get('author', 'unknown'),)
        
        if cluster_key not in clusters:
            clusters[cluster_key] = []
        clusters[cluster_key].append(post)
    
    return clusters

def generate_summary(posts):
    """生成中文摘要（简化版，实际可用AI生成）"""
    if not posts:
        return ""
    
    # 提取共同主题
    all_content = " ".join([p.get('title', '') + " " + p.get('content', '') for p in posts])
    keywords = extract_keywords(all_content)
    
    # 统计用户观点
    authors = list(set([p.get('author', 'Unknown') for p in posts]))
    
    # 生成简单摘要
    main_topic = keywords[0] if keywords else "相关话题"
    summary = f"X用户热议{main_topic}。"
    
    # 添加用户数量信息
    if len(authors) > 1:
        summary += f"{len(authors)}位用户参与讨论，"
    
    # 添加帖子数量
    summary += f"共{len(posts)}条相关帖子。"
    
    # 简单情感/趋势判断
    positive_words = ['great', 'amazing', 'awesome', 'good', 'love', 'excited', 'bullish']
    negative_words = ['bad', 'terrible', 'awful', 'hate', 'bearish', 'concerned', 'worried']
    
    content_lower = all_content.lower()
    pos_count = sum(1 for w in positive_words if w in content_lower)
    neg_count = sum(1 for w in negative_words if w in content_lower)
    
    if pos_count > neg_count:
        summary += "整体情绪偏向积极。"
    elif neg_count > pos_count:
        summary += "整体情绪偏向谨慎。"
    else:
        summary += "观点较为多元。"
    
    return summary

def parse_x_events(rss_items):
    """解析 RSS 条目为 X 事件格式"""
    # 聚类
    clusters = cluster_posts(rss_items)
    
    events = []
    event_id = 1
    
    for cluster_key, posts in clusters.items():
        if len(posts) < 1:  # 至少1条帖子
            continue
        
        # 生成事件标题（使用第一个帖子的标题或关键词）
        first_post = posts[0]
        title = first_post.get('title', '')
        
        # 如果标题太长，截断
        if len(title) > 60:
            title = title[:57] + '...'
        
        # 提取用户列表（从dc:creator中提取用户名）
        users = []
        for p in posts:
            author = p.get('author', '')
            # 作者格式已经是 @username
            if author.startswith('@'):
                users.append(author)
            else:
                users.append(f"@{author}")
        users = list(set(users))  # 去重
        
        # 生成摘要
        summary = generate_summary(posts)
        
        # 收集真实的帖子URL和最新的时间
        urls = []
        latest_time = None
        for p in posts:
            url = p.get('url', '')
            if url and 'status/' in url:
                urls.append(url)
            
            # 获取最新的时间
            pub_time = p.get('time', '')
            if pub_time:
                try:
                    from email.utils import parsedate_to_datetime
                    dt = parsedate_to_datetime(pub_time)
                    if latest_time is None or dt > latest_time:
                        latest_time = dt
                except:
                    pass
        
        # 格式化更新时间
        update_time_str = ''
        if latest_time:
            update_time_str = latest_time.strftime('%Y-%m-%d %H:%M')
        
        # 如果没有URL，使用列表链接作为fallback
        if not urls:
            urls = ["https://x.com/i/lists/1673520347939995648"]
        
        events.append({
            "id": f"x-{event_id}",
            "title": title,
            "summary": summary,
            "users": users[:10],  # 最多10个用户
            "postCount": len(posts),
            "updateTime": update_time_str,
            "urls": urls[:10]  # 最多10个链接
        })
        
        event_id += 1
    
    # 按帖子数排序
    events.sort(key=lambda x: x['postCount'], reverse=True)
    
    return events[:30]  # 最多30个事件

def get_version():
    """生成版本号: YYYY.MM.DD-NNN"""
    now = datetime.now()
    return now.strftime('%Y.%m.%d-001')

def update_github_page(x_events):
    """更新 GitHub Pages 页面，保留当天之前的内容"""
    # 获取现有存档
    archive = get_current_archive()
    
    today = datetime.now().strftime('%Y-%m-%d')
    version = get_version()
    
    # 更新今天的事件（追加模式）
    if today not in archive:
        archive[today] = []
    
    # 合并新事件（去重）
    existing_titles = {e['title'] for e in archive[today]}
    for event in x_events:
        if event['title'] not in existing_titles:
            archive[today].append(event)
    
    # 只保留最近 7 天的数据
    sorted_dates = sorted(archive.keys())
    if len(sorted_dates) > 7:
        for old_date in sorted_dates[:-7]:
            del archive[old_date]
    
    # 读取本地 HTML 模板
    with open(LOCAL_FILE, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 替换 X_EVENTS_ARCHIVE
    archive_json = json.dumps(archive, ensure_ascii=False, indent=16)
    pattern = r'const X_EVENTS_ARCHIVE = \{[\s\S]*?\};'
    replacement = f'const X_EVENTS_ARCHIVE = {archive_json};'
    updated_html = re.sub(pattern, replacement, html_content)
    
    # 更新版本号
    version_pattern = r'版本: [\d\.]+-\d+'
    version_replacement = f'版本: {version}'
    updated_html = re.sub(version_pattern, version_replacement, updated_html)
    
    # 获取文件 SHA
    sha, _ = get_file_sha()
    if not sha:
        print("错误：无法获取文件 SHA")
        return False
    
    # 上传到 GitHub
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {
        "Authorization": f"token {GITHUB_TOKEN}",
        "Accept": "application/vnd.github.v3+json"
    }
    
    content_b64 = base64.b64encode(updated_html.encode('utf-8')).decode('utf-8')
    
    data = {
        "message": f"[{version}] Update X events: {today} ({len(archive.get(today, []))} topics)",
        "content": content_b64,
        "sha": sha,
        "branch": "main"
    }
    
    response = requests.put(url, headers=headers, json=data, timeout=30)
    
    if response.status_code in [200, 201]:
        print(f"✅ X 事件更新成功")
        print(f"   日期: {today}")
        print(f"   事件数量: {len(archive.get(today, []))} 个")
        print(f"   历史天数: {len(archive)} 天")
        return True
    else:
        print(f"❌ 更新失败: {response.status_code} - {response.text[:200]}")
        return False

def main():
    """主函数"""
    print("=" * 50)
    print("X RSS 事件聚合任务")
    print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 50)
    
    # 获取 RSS
    print("\n[1/3] 获取 RSS 内容...")
    rss_items = fetch_rss()
    if not rss_items:
        print("⚠️  未获取到 RSS 内容")
        return 1
    print(f"   获取到 {len(rss_items)} 条 RSS 条目")
    
    # 聚类并生成事件
    print("\n[2/3] 聚类并生成事件摘要...")
    x_events = parse_x_events(rss_items)
    print(f"   聚合成 {len(x_events)} 个事件")
    
    if x_events:
        print("\n   热门事件预览:")
        for i, event in enumerate(x_events[:3], 1):
            print(f"   {i}. {event['title'][:40]}... ({event['postCount']}帖子)")
    
    # 更新 GitHub Pages
    print("\n[3/3] 更新 GitHub Pages...")
    success = update_github_page(x_events)
    
    if success:
        print(f"\n✅ 完成!")
        print(f"页面地址: https://mutjan.github.io/x-reader/")
        return 0
    else:
        print(f"\n❌ 失败")
        return 1

if __name__ == '__main__':
    exit(main())
