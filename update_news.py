#!/usr/bin/env python3
"""
Inoreader 新闻摘要生成器
用于更新 GitHub Pages 上的新闻页面
"""

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 配置
INOREADER_FILE = os.path.expanduser("~/inoreader_export.json")  # 用户提供的 Inoreader 导出文件
TEMPLATE_FILE = Path(__file__).parent / "index_template.html"
OUTPUT_FILE = Path(__file__).parent / "index.html"

def parse_inoreader_data(file_path):
    """解析 Inoreader 导出文件"""
    if not os.path.exists(file_path):
        print(f"错误：找不到文件 {file_path}")
        return None
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except Exception as e:
        print(f"解析文件出错: {e}")
        return None

def categorize_news(items):
    """对新闻进行分类"""
    hot = []
    ai = []
    tech = []
    business = []
    
    # AI 相关关键词
    ai_keywords = ['AI', 'artificial intelligence', 'LLM', 'GPT', 'Claude', 'OpenAI', 
                   'Anthropic', '大模型', '机器学习', '深度学习', '神经网络']
    
    # 商业相关关键词
    business_keywords = ['融资', 'IPO', '收购', '并购', '投资', '股价', '财报', 
                        'revenue', 'funding', 'acquisition', 'stock', 'earnings']
    
    for item in items:
        title = item.get('title', '')
        summary = item.get('summary', '')
        text = f"{title} {summary}".lower()
        
        # 热度判断（根据点赞/分享数，这里简化处理）
        is_hot = item.get('engagement', 0) > 50 or 'breaking' in text or '重磅' in title
        
        news_item = {
            'title': title,
            'url': item.get('url', ''),
            'source': item.get('source', 'Unknown'),
            'summary': summary[:200] + '...' if len(summary) > 200 else summary,
            'time': item.get('published', ''),
            'tags': item.get('tags', [])
        }
        
        # 分类
        if any(kw.lower() in text for kw in ai_keywords):
            ai.append(news_item)
        elif any(kw.lower() in text for kw in business_keywords):
            business.append(news_item)
        else:
            tech.append(news_item)
        
        if is_hot:
            hot.append(news_item)
    
    # 限制数量
    return {
        'hot': hot[:8],
        'ai': ai[:6],
        'tech': tech[:8],
        'business': business[:6]
    }

def generate_news_data():
    """生成新闻数据 JSON"""
    data = parse_inoreader_data(INOREADER_FILE)
    
    if not data:
        # 返回空数据结构
        return {
            'date': datetime.now().strftime('%Y-%m-%d'),
            'updateTime': datetime.now().strftime('%Y-%m-%d %H:%M'),
            'hot': [],
            'ai': [],
            'tech': [],
            'business': []
        }
    
    items = data.get('items', [])
    categorized = categorize_news(items)
    
    return {
        'date': datetime.now().strftime('%Y-%m-%d'),
        'updateTime': datetime.now().strftime('%Y-%m-%d %H:%M'),
        **categorized
    }

def update_html_page():
    """更新 HTML 页面中的新闻数据"""
    news_data = generate_news_data()
    
    # 读取当前 HTML
    with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
        html_content = f.read()
    
    # 替换 NEWS_DATA
    news_json = json.dumps(news_data, ensure_ascii=False, indent=4)
    
    # 使用正则替换 NEWS_DATA 对象
    pattern = r'const NEWS_DATA = \{[^}]*\};'
    replacement = f'const NEWS_DATA = {news_json};'
    
    updated_html = re.sub(pattern, replacement, html_content, flags=re.DOTALL)
    
    # 如果没有匹配到，尝试另一种格式
    if updated_html == html_content:
        pattern = r'const NEWS_DATA = \{[\s\S]*?\};'
        updated_html = re.sub(pattern, replacement, html_content)
    
    # 保存更新后的 HTML
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write(updated_html)
    
    print(f"页面已更新: {OUTPUT_FILE}")
    print(f"更新时间: {news_data['updateTime']}")
    print(f"热点新闻: {len(news_data['hot'])} 条")
    print(f"AI 新闻: {len(news_data['ai'])} 条")
    print(f"科技新闻: {len(news_data['tech'])} 条")
    print(f"商业新闻: {len(news_data['business'])} 条")

def main():
    """主函数"""
    print("=" * 50)
    print("Inoreader 新闻摘要生成器")
    print("=" * 50)
    
    # 检查 Inoreader 文件
    if not os.path.exists(INOREADER_FILE):
        print(f"\n⚠️  警告: 找不到 Inoreader 数据文件")
        print(f"   期望路径: {INOREADER_FILE}")
        print(f"\n请提供 Inoreader 导出文件，或运行 inoreader_daily_proxy.py 获取数据")
        
        # 仍然更新页面，但使用空数据
        update_html_page()
        return
    
    # 更新页面
    update_html_page()
    
    print("\n✅ 完成!")

if __name__ == '__main__':
    main()
