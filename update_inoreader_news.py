#!/usr/bin/env python3
"""
Inoreader 新闻更新脚本 - 每小时更新 GitHub Pages
简化版本：使用原标题，添加中文前缀标签
"""

import json
import subprocess
import os
import re
from datetime import datetime, timedelta
import time

INOREADER_API = "https://www.inoreader.com/reader/api/0"
PROXY = "socks5h://127.0.0.1:1080"

# 重点关注的科技领域
FOCUS_AREAS = {
    "AI和机器人": {
        "keywords": [
            "AI", "artificial intelligence", "machine learning", "deep learning", "neural network",
            "LLM", "large language model", "GPT", "Claude", "Gemini", "Llama", "Mistral",
            "OpenAI", "Anthropic", "DeepMind", "xAI", "Mira", "robot", "robotics",
            "autonomous", "agent", "coding agent", "AI agent", "multimodal",
            "computer vision", "NLP", "natural language processing",
            "人形机器人", "具身智能", "大模型", "人工智能", "机器学习"
        ],
        "weight": 15
    },
    "基础科学": {
        "keywords": [
            "mathematics", "math", "physics", "quantum physics", "theoretical physics",
            "pure mathematics", "number theory", "topology", "algebra", "geometry",
            "cosmology", "astrophysics", "particle physics", "string theory",
            "数学", "物理", "量子物理", "理论物理", "纯数学", "宇宙学"
        ],
        "weight": 12
    },
    "商业航天": {
        "keywords": [
            "SpaceX", "Starship", "Falcon", "Starlink", "space", "rocket", "satellite",
            "Blue Origin", "ULA", "Boeing Starliner", "Orion", "Artemis",
            "commercial space", "space station", "Mars mission", "lunar",
            "太空", "航天", "火箭", "卫星", "商业航天", "火星任务", "登月"
        ],
        "weight": 12
    },
    "量子计算": {
        "keywords": [
            "quantum computing", "quantum computer", "qubit", "quantum processor",
            "IBM Quantum", "Google Quantum", "quantum supremacy", "quantum advantage",
            "quantum error correction", "quantum algorithm", "NISQ",
            "量子计算", "量子计算机", "量子比特", "量子霸权", "量子优势"
        ],
        "weight": 12
    }
}

# 降低权重的领域
REDUCE_WEIGHT_AREAS = {
    "消费电子": ["smartphone", "iPhone", "Samsung Galaxy", "Pixel", "OnePlus", "Xiaomi", "OPPO", "vivo",
                "手机", "智能手机", "耳机", "平板", "手表", "可穿戴"],
    "一般商业": ["earnings", "revenue", "profit", "stock price", "market cap", "IPO", "valuation",
                "财报", "营收", "利润", "股价", "市值", "估值"],
    "汽车": ["EV", "electric vehicle", "Tesla Model", "BYD", "NIO", "Li Auto", "XPeng",
             "电动车", "新能源汽车", "电动汽车", "车型", "续航"]
}

# 重要事件关键词
IMPORTANT_PATTERNS = {
    "人员变动": [
        r"joins?\s+(OpenAI|Anthropic|Google|DeepMind|xAI|SpaceX|Tesla|Meta|Microsoft|Apple)",
        r"joins?\s+(\w+)\s+as\s+(CEO|CTO|Chief|Head|VP)",
        r"leaves?\s+(OpenAI|Anthropic|Google|DeepMind|xAI|SpaceX|Tesla|Meta|Microsoft|Apple)",
        r"(Sam Altman|Demis Hassabis|Elon Musk|Mark Zuckerberg|Satya Nadella)\s+(joins?|leaves?|steps?\s+down)",
        r"离职", r"加入", r"入职", r"任命", r"首席", r"负责人"
    ],
    "重大突破": [
        r"breakthrough", r"milestone", r"state[-\s]of[-\s]the[-\s]art", r"SOTA",
        r"first\s+time", r"world[-\s]first", r"record[-\s]breaking",
        r"重大突破", r"里程碑", r"首次", r"创纪录", r"世界第一"
    ],
    "重要论文": [
        r"Nature", r"Science", r"Cell", r"PNAS", r"arxiv\s*:\s*\d+",
        r"published\s+in\s+(Nature|Science|Cell)",
        r"论文发表", r"研究成果", r"学术论文"
    ]
}

# 重要公司/人物
HIGH_PRIORITY_ENTITIES = [
    "OpenAI", "Anthropic", "Google", "Microsoft", "Apple", "Meta", "Amazon",
    "Nvidia", "AMD", "Intel", "Tesla", "SpaceX", "xAI", "DeepMind",
    "Sam Altman", "Satya Nadella", "Sundar Pichai", "Tim Cook", "Mark Zuckerberg",
    "Elon Musk", "Jensen Huang", "Demis Hassabis", "Dario Amodei",
]

def curl_request(url, headers=None, timeout=30):
    cmd = ["curl", "-s", "--connect-timeout", str(timeout), "--max-time", str(timeout * 2), "--socks5-hostname", PROXY, "-k", url]
    if headers:
        for key, value in headers.items():
            cmd.extend(["-H", f"{key}: {value}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout

def get_token():
    config_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
    with open(config_path) as f:
        config = json.load(f)
    return config.get("inoreader", {}).get("access_token")

def get_recent_items(token, hours=1, limit=50):
    since = int(time.time()) - (hours * 3600)
    url = f"{INOREADER_API}/stream/contents/user/-/state/com.google/reading-list?n={limit}&ot={since}"
    response = curl_request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(response)

def analyze_importance(item):
    """分析文章重要性"""
    title = item.get("title", "")
    summary = item.get("summary", {}).get("content", "")
    text = f"{title} {summary}".lower()
    text_original = f"{title} {summary}"
    
    found_categories = []
    priority_score = 0
    
    # 1. 检查重点领域的匹配
    for area_name, area_config in FOCUS_AREAS.items():
        for keyword in area_config["keywords"]:
            if keyword.lower() in text:
                priority_score += area_config["weight"]
                if area_name not in found_categories:
                    found_categories.append(area_name)
                break
    
    # 2. 检查重要事件模式
    for category, patterns in IMPORTANT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, text_original, re.IGNORECASE):
                if category not in found_categories:
                    found_categories.append(category)
                priority_score += 8
                break
    
    # 3. 检查是否是需要降低权重的领域
    penalty = 0
    for area_name, keywords in REDUCE_WEIGHT_AREAS.items():
        if any(kw.lower() in text for kw in keywords):
            penalty += 5
    
    priority_score = max(0, priority_score - penalty)
    
    # 4. 重要人物/公司加分
    for entity in HIGH_PRIORITY_ENTITIES:
        if entity.lower() in text:
            priority_score += 3
    
    # 5. 高优先级来源加分
    high_priority_sources = ["TechCrunch", "The Verge", "Ars Technica", "Hacker News", "Techmeme", "Nature", "Science"]
    origin = item.get("origin", {})
    source_title = origin.get("title", "")
    for source in high_priority_sources:
        if source.lower() in source_title.lower():
            priority_score += 2
            break
    
    # 重点领域内容更容易通过
    is_important = priority_score >= 12
    
    return is_important, found_categories, priority_score, title, summary

def get_type_info(categories, score):
    """根据类别和分数确定新闻类型"""
    if score >= 30:
        return "hot", "热点"
    elif "AI和机器人" in categories or "量子计算" in categories:
        return "ai", "AI"
    elif "基础科学" in categories or "商业航天" in categories:
        return "tech", "科技"
    else:
        return "business", "商业"

def generate_chinese_label(title, summary_text, categories):
    """生成中文标签前缀"""
    full_text = f"{title} {summary_text}".lower()
    
    labels = []
    
    # 检测关键实体
    companies = ['openai', 'anthropic', 'google', 'microsoft', 'apple', 'meta', 'tesla', 'spacex', 'nvidia']
    persons = ['sam altman', 'elon musk', 'mark zuckerberg', 'dario amodei', 'satya nadella']
    
    for p in persons:
        if p in full_text:
            name = p.title().replace('Sam Altman', 'Sam Altman').replace('Elon Musk', '马斯克')
            labels.append(name)
            break
    
    if not labels:
        for c in companies:
            if c in full_text:
                labels.append(c.title().replace('Openai', 'OpenAI').replace('Anthropic', 'Anthropic'))
                break
    
    # 检测事件类型
    if any(w in full_text for w in ['joins', 'hired', 'appointed', 'ceo', 'chief', '离职', '任命']):
        labels.append('人事')
    elif any(w in full_text for w in ['funding', 'raised', 'billion', '融资', '估值']):
        labels.append('融资')
    elif any(w in full_text for w in ['launch', 'release', 'announced', '发布', '推出']):
        labels.append('新品')
    elif any(w in full_text for w in ['breakthrough', 'discover', '突破', '发现']):
        labels.append('突破')
    elif any(w in full_text for w in ['paper', 'research', 'nature', 'science', '论文']):
        labels.append('论文')
    elif any(w in full_text for w in ['safety', 'concern', 'risk', '争议']):
        labels.append('争议')
    
    # 类别标签
    category_label = ""
    if "基础科学" in categories:
        category_label = "【科研】"
    elif "量子计算" in categories:
        category_label = "【量子】"
    elif "商业航天" in categories:
        category_label = "【航天】"
    elif "AI和机器人" in categories:
        category_label = "【AI】"
    
    if labels:
        return f"{category_label}{'|'.join(labels)}："
    return category_label

def clean_html(html_text):
    """清理HTML标签，提取纯文本摘要"""
    if not html_text:
        return ""
    
    # 移除script和style标签及其内容
    text = re.sub(r'<(script|style)[^>]*>[^<]*</\1>', ' ', html_text, flags=re.IGNORECASE)
    
    # 移除img标签
    text = re.sub(r'<img[^>]*>', ' ', text, flags=re.IGNORECASE)
    
    # 移除所有HTML标签
    text = re.sub(r'<[^>]+>', ' ', text)
    
    # 移除URL
    text = re.sub(r'https?://\S+', '', text)
    
    # 移除多余空白
    text = ' '.join(text.split())
    
    # 截取前150个字符作为摘要
    if len(text) > 150:
        text = text[:147] + "..."
    
    return text.strip()

def process_items(items):
    """处理条目"""
    processed = []
    
    for item in items:
        is_important, categories, score, title, summary = analyze_importance(item)
        
        if not is_important:
            continue
        
        # 获取类型
        news_type, type_name = get_type_info(categories, score)
        
        # 获取来源信息
        origin = item.get("origin", {})
        source_title = origin.get("title", "未知来源")
        
        # 获取链接
        links = item.get("alternate", [])
        link = links[0].get("href", "") if links else ""
        
        # 生成中文标签
        label = generate_chinese_label(title, summary, categories)
        
        # 清理标题
        clean_title = title
        clean_title = re.sub(r'^(RT|MT)\s*[@\w]+:\s*', '', clean_title, flags=re.IGNORECASE)
        clean_title = re.sub(r'^[@\w]+:\s*', '', clean_title)
        clean_title = re.sub(r'https?://\S+', '', clean_title)
        clean_title = ' '.join(clean_title.split())
        
        # 清理摘要 - 移除HTML标签和图片
        clean_summary = clean_html(summary)
        
        processed.append({
            "title": f"{label}{clean_title}",
            "originalTitle": title,
            "summary": clean_summary,
            "type": news_type,
            "typeName": type_name,
            "sources": 1,
            "sourceLinks": [{"name": source_title, "url": link}],
            "categories": categories,
            "score": score,
            "timestamp": item.get("published", 0)
        })
    
    return processed

def calculate_similarity(s1, s2):
    """计算两个字符串的相似度"""
    s1_lower = s1.lower()
    s2_lower = s2.lower()
    
    # 直接包含检查
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8
    
    # 提取关键词
    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}
    
    def extract_keywords(text):
        cleaned = re.sub(r'[^\w\s]', ' ', text.lower())
        words = cleaned.split()
        return set(w for w in words if len(w) > 2 and w not in stop_words)
    
    keywords1 = extract_keywords(s1)
    keywords2 = extract_keywords(s2)
    
    if not keywords1 or not keywords2:
        return 0
    
    intersection = len(keywords1 & keywords2)
    union = len(keywords1 | keywords2)
    
    if union == 0:
        return 0
    
    return intersection / union

def merge_similar_news(news_list):
    """合并相似新闻"""
    if not news_list:
        return []
    
    groups = []
    used = set()
    
    for i, news in enumerate(news_list):
        if i in used:
            continue
        
        group = [news]
        used.add(i)
        
        title1 = news.get("originalTitle", news["title"]).lower()
        
        for j, other in enumerate(news_list[i+1:], i+1):
            if j in used:
                continue
            
            title2 = other.get("originalTitle", other["title"]).lower()
            
            similarity = calculate_similarity(title1, title2)
            
            if similarity > 0.5:
                group.append(other)
                used.add(j)
        
        # 合并组内新闻
        merged = group[0].copy()
        merged["sources"] = len(group)
        merged["sourceLinks"] = []
        seen_urls = set()
        
        for item in group:
            for link in item["sourceLinks"]:
                if link["url"] not in seen_urls:
                    merged["sourceLinks"].append(link)
                    seen_urls.add(link["url"])
        
        merged["score"] = max(item["score"] for item in group)
        
        groups.append(merged)
    
    groups.sort(key=lambda x: x["score"], reverse=True)
    
    return groups

def update_github_pages(news_data):
    """更新 GitHub Pages"""
    try:
        print("\n[GitHub Pages] 开始更新...")
        
        today = datetime.now().strftime('%Y-%m-%d')
        
        data_file = "news_data.json"
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                archive = json.load(f)
        else:
            archive = {}
        
        archive[today] = news_data
        
        dates = sorted(archive.keys())
        if len(dates) > 30:
            for old_date in dates[:-30]:
                del archive[old_date]
        
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
        
        print(f"[GitHub Pages] 数据已保存: {today}, {len(news_data)} 条新闻")
        
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "OpenClaw Bot"
        env["GIT_AUTHOR_EMAIL"] = "bot@openclaw.ai"
        env["GIT_COMMITTER_NAME"] = "OpenClaw Bot"
        env["GIT_COMMITTER_EMAIL"] = "bot@openclaw.ai"
        
        subprocess.run(["git", "add", data_file], check=True, env=env)
        
        result = subprocess.run(
            ["git", "commit", "-m", f"Update news data for {today}"],
            capture_output=True,
            text=True,
            env=env
        )
        
        if result.returncode == 0 or "nothing to commit" in result.stderr.lower():
            push_result = subprocess.run(
                ["git", "push", "origin", "main"],
                capture_output=True,
                text=True,
                env=env
            )
            
            if push_result.returncode == 0:
                print("[GitHub Pages] ✅ 更新成功")
                return True
            else:
                print(f"[GitHub Pages] ⚠️ 推送失败: {push_result.stderr}")
                return False
        else:
            print(f"[GitHub Pages] ⚠️ 提交失败: {result.stderr}")
            return False
            
    except Exception as e:
        print(f"[GitHub Pages] ❌ 更新出错: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主函数"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始更新 Inoreader 新闻...")
    
    try:
        token = get_token()
        
        print("获取最近24小时的内容...")
        items = get_recent_items(token, hours=24, limit=200)
        
        print(f"获取到 {len(items.get('items', []))} 条内容")
        
        processed = process_items(items.get("items", []))
        print(f"重要内容: {len(processed)} 条")
        
        merged = merge_similar_news(processed)
        print(f"合并后: {len(merged)} 条")
        
        if merged:
            update_github_pages(merged)
        else:
            print("没有重要新闻需要更新")
        
        print(f"\n✅ 完成!")
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
