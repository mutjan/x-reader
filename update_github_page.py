#!/usr/bin/env python3
"""
更新 GitHub Pages 新闻页面 - 多消息源版本
由定时任务调用
"""

import json
import base64
import requests
import re
from datetime import datetime
from pathlib import Path

# 配置
GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN', '')
REPO = "mutjan/x-reader"
FILE_PATH = "index.html"
LOCAL_FILE = "/root/.openclaw/workspace/x_reader/index.html"

def get_file_sha():
    """获取文件的当前 SHA"""
    url = f"https://api.github.com/repos/{REPO}/contents/{FILE_PATH}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json().get('sha'), response.json().get('content')
    return None, None

def get_current_archive():
    """从当前页面获取 NEWS_ARCHIVE 数据"""
    sha, content_b64 = get_file_sha()
    if not content_b64:
        return {}
    
    try:
        content = base64.b64decode(content_b64).decode('utf-8')
        # 提取 NEWS_ARCHIVE
        match = re.search(r'const NEWS_ARCHIVE = \{([\s\S]*?)\};', content)
        if match:
            archive_str = '{' + match.group(1) + '}'
            return json.loads(archive_str)
    except Exception as e:
        print(f"解析现有数据出错: {e}")
    
    return {}

def categorize_and_format(items):
    """将新闻分类并格式化为新数据格式"""
    formatted = []
    
    # 分类关键词
    hot_keywords = ['Meta', 'OpenAI', 'Apple', 'Google', 'Microsoft', 'Nvidia', 'AMD', '重磅', '突发']
    ai_keywords = ['AI', '人工智能', 'LLM', 'GPT', 'Claude', '大模型', '机器学习']
    business_keywords = ['融资', 'IPO', '收购', '估值', '财报', '营收', '美元', '亿元']
    
    for item in items:
        title = item.get('title', '')
        summary = item.get('summary', '')
        text = f"{title} {summary}".lower()
        
        # 判断类型
        if any(kw in title for kw in hot_keywords):
            item_type = 'hot'
            type_name = '热点'
        elif any(kw.lower() in text for kw in ai_keywords):
            item_type = 'ai'
            type_name = 'AI'
        elif any(kw in text for kw in business_keywords):
            item_type = 'business'
            type_name = '商业'
        else:
            item_type = 'tech'
            type_name = '科技'
        
        # 构建消息源链接列表
        source_links = []
        
        # 主链接
        main_url = item.get('url', '')
        main_source = item.get('source', 'Source')
        if main_url:
            source_links.append({"name": main_source, "url": main_url})
        
        # 额外来源（如果有）
        extra_sources = item.get('extraSources', [])
        for src in extra_sources:
            if isinstance(src, dict):
                source_links.append(src)
            elif isinstance(src, str):
                # 尝试解析 "Name: URL" 格式
                if ':' in src:
                    parts = src.split(':', 1)
                    source_links.append({"name": parts[0].strip(), "url": parts[1].strip()})
        
        # 去重
        seen_urls = set()
        unique_links = []
        for link in source_links:
            if link['url'] not in seen_urls:
                seen_urls.add(link['url'])
                unique_links.append(link)
        
        formatted.append({
            "type": item_type,
            "typeName": type_name,
            "title": title,
            "summary": summary[:150] + '...' if len(summary) > 150 else summary,
            "sources": len(unique_links),
            "sourceLinks": unique_links
        })
    
    return formatted

def update_github_page(news_items):
    """更新 GitHub Pages 页面，保留历史数据"""
    # 获取现有存档
    archive = get_current_archive()
    
    # 格式化新数据
    today = datetime.now().strftime('%Y-%m-%d')
    formatted_items = categorize_and_format(news_items)
    
    # 添加新数据
    archive[today] = formatted_items
    
    # 只保留最近 30 天的数据
    sorted_dates = sorted(archive.keys())
    if len(sorted_dates) > 30:
        for old_date in sorted_dates[:-30]:
            del archive[old_date]
    
    # 读取本地 HTML 模板
    with open(LOCAL_FILE, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 替换 NEWS_ARCHIVE
    archive_json = json.dumps(archive, ensure_ascii=False, indent=16)
    pattern = r'const NEWS_ARCHIVE = \{[\s\S]*?\};'
    replacement = f'const NEWS_ARCHIVE = {archive_json};'
    updated_html = re.sub(pattern, replacement, html_content)
    
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
        "message": f"Update news: {today}",
        "content": content_b64,
        "sha": sha,
        "branch": "main"
    }
    
    response = requests.put(url, headers=headers, json=data)
    
    if response.status_code in [200, 201]:
        print(f"✅ 页面更新成功")
        print(f"   新增日期: {today}")
        print(f"   新闻数量: {len(formatted_items)} 条")
        print(f"   历史数据: {len(archive)} 天")
        return True
    else:
        print(f"❌ 更新失败: {response.status_code} - {response.text}")
        return False

def main():
    """主函数"""
    import sys
    
    if len(sys.argv) > 1:
        # 从命令行参数读取 JSON
        news_items = json.loads(sys.argv[1])
    else:
        # 使用默认空数据
        news_items = []
    
    print("更新 GitHub Pages 新闻页面...")
    print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    success = update_github_page(news_items)
    
    if success:
        print(f"\n页面地址: https://mutjan.github.io/x-reader/")
    
    return 0 if success else 1

if __name__ == '__main__':
    exit(main())
