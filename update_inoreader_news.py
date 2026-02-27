#!/usr/bin/env python3
"""
Inoreader 新闻更新脚本 - 每小时更新 GitHub Pages
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

def generate_summary(title, summary_text):
    """生成中文摘要"""
    full_text = f"{title} {summary_text}".strip()
    full_text = re.sub(r'https?://\S+', '', full_text)
    full_text = re.sub(r'<[^>]+>', '', full_text)
    full_text = full_text.strip()
    
    if not full_text:
        return "相关内容"
    
    # 提取关键实体
    entities = []
    entity_patterns = [
        (r'\b(OpenAI|Anthropic|Google|Microsoft|Apple|Meta|Amazon|Nvidia|AMD|Intel|Tesla|SpaceX|xAI|DeepMind)\b', '公司'),
        (r'\b(Sam Altman|Elon Musk|Mark Zuckerberg|Satya Nadella|Sundar Pichai|Tim Cook|Jensen Huang)\b', '人物'),
        (r'\b(Claude|GPT|ChatGPT|Gemini|Llama|Copilot|Siri|Alexa)\b', '产品'),
    ]
    
    for pattern, entity_type in entity_patterns:
        matches = re.findall(pattern, full_text, re.IGNORECASE)
        for match in matches:
            if match not in [e[0] for e in entities]:
                entities.append((match, entity_type))
    
    # 检测动作
    action_patterns = {
        '发布': ['launch', 'release', 'announce', 'introduce', 'unveil', '发布', '推出', '上线'],
        '收购': ['acquire', 'buy', 'purchase', '并购', '收购'],
        '投资': ['invest', 'fund', 'investment', '融资', '投资'],
        '合作': ['partner', 'collaborate', 'partnership', '合作', '联手'],
        '离职': ['leave', 'depart', 'resign', 'quit', '离职', '辞职'],
        '加入': ['join', 'hire', 'appoint', '入职', '加入'],
    }
    
    detected_action = ""
    for action, keywords in action_patterns.items():
        if any(kw.lower() in full_text.lower() for kw in keywords):
            detected_action = action
            break
    
    main_entity = entities[0][0] if entities else ""
    
    if main_entity and detected_action:
        return f"{main_entity}{detected_action}相关动态"
    elif main_entity:
        return f"关于{main_entity}的最新动态"
    else:
        core = full_text[:50] if len(full_text) <= 50 else full_text[:47] + "..."
        return f"{core}"

def process_items(items):
    """处理条目并聚类"""
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
        
        processed.append({
            "title": title,
            "summary": generate_summary(title, summary),
            "type": news_type,
            "typeName": type_name,
            "sources": 1,
            "sourceLinks": [{"name": source_title, "url": link}],
            "categories": categories,
            "score": score,
            "timestamp": item.get("published", 0)
        })
    
    return processed

def merge_similar_news(news_list):
    """合并相似新闻"""
    if not news_list:
        return []
    
    # 按标题相似度分组
    groups = []
    used = set()
    
    for i, news in enumerate(news_list):
        if i in used:
            continue
        
        group = [news]
        used.add(i)
        
        title1 = news["title"].lower()
        
        for j, other in enumerate(news_list[i+1:], i+1):
            if j in used:
                continue
            
            title2 = other["title"].lower()
            
            # 简单相似度检查
            similarity = calculate_similarity(title1, title2)
            
            if similarity > 0.6:
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
        
        # 取最高分
        merged["score"] = max(item["score"] for item in group)
        
        groups.append(merged)
    
    # 按分数排序
    groups.sort(key=lambda x: x["score"], reverse=True)
    
    return groups

def calculate_similarity(s1, s2):
    """计算两个字符串的相似度"""
    # 简单的 Jaccard 相似度
    set1 = set(s1.split())
    set2 = set(s2.split())
    
    if not set1 or not set2:
        return 0
    
    intersection = len(set1 & set2)
    union = len(set1 | set2)
    
    return intersection / union if union > 0 else 0

def update_github_pages(news_data):
    """更新 GitHub Pages"""
    try:
        print("\n[GitHub Pages] 开始更新...")
        
        # 获取当前日期
        today = datetime.now().strftime('%Y-%m-%d')
        
        # 读取现有数据
        data_file = "news_data.json"
        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                archive = json.load(f)
        else:
            archive = {}
        
        # 更新今天的数据
        archive[today] = news_data
        
        # 只保留最近 30 天的数据
        dates = sorted(archive.keys())
        if len(dates) > 30:
            for old_date in dates[:-30]:
                del archive[old_date]
        
        # 保存数据
        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)
        
        print(f"[GitHub Pages] 数据已保存: {today}, {len(news_data)} 条新闻")
        
        # Git 提交
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "OpenClaw Bot"
        env["GIT_AUTHOR_EMAIL"] = "bot@openclaw.ai"
        env["GIT_COMMITTER_NAME"] = "OpenClaw Bot"
        env["GIT_COMMITTER_EMAIL"] = "bot@openclaw.ai"
        
        # 添加文件
        subprocess.run(["git", "add", data_file], check=True, env=env)
        
        # 提交
        result = subprocess.run(
            ["git", "commit", "-m", f"Update news data for {today}"],
            capture_output=True,
            text=True,
            env=env
        )
        
        if result.returncode == 0 or "nothing to commit" in result.stderr.lower():
            # 推送
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
        
        print("获取最近1小时的内容...")
        items = get_recent_items(token, hours=1, limit=50)
        
        print(f"获取到 {len(items.get('items', []))} 条内容")
        
        # 处理条目
        processed = process_items(items.get("items", []))
        print(f"重要内容: {len(processed)} 条")
        
        # 合并相似新闻
        merged = merge_similar_news(processed)
        print(f"合并后: {len(merged)} 条")
        
        # 更新 GitHub Pages
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
