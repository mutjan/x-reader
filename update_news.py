#!/usr/bin/env python3
"""
量子位风格新闻选题更新脚本 v2.1
- 多源聚合优先：同一事件多源报道自动聚合并加分
- 纯中文标题：量子位风格，不带类型前缀
- 智能摘要：优先抓取原文生成一句话总结
"""

import json
import subprocess
import os
import re
from datetime import datetime, timedelta
import time
from urllib.parse import urlparse

# ==================== 配置 ====================

INOREADER_API = "https://www.inoreader.com/reader/api/0"
PROXY = "socks5h://127.0.0.1:7890"

# ==================== 量子位风格选题规则 ====================

# S级选题：必报（高传播保障）
S_LEVEL_TOPICS = {
    "AI大模型重大发布": {
        "keywords": [
            "GPT-4", "GPT-4o", "Claude", "Gemini", "Llama", "Sora", "o1", "o3", "DeepSeek",
            "大模型发布", "多模态模型", "视频生成模型", "AI Agent", "AutoGPT",
        ],
        "patterns": [r"GPT-\d+", r"Claude \d+", r"Gemini \d+", r"发布.*模型", r"推出.*大模型"],
        "weight": 100,
    },
    "马斯克/SpaceX动态": {
        "keywords": ["马斯克", "Elon Musk", "Musk", "SpaceX", "Starship", "星舰", "Falcon", "载人航天"],
        "patterns": [r"SpaceX.*成功", r"马斯克.*创造", r"星舰.*发射", r"Falcon.*火箭"],
        "weight": 95,
    },
    "Nature/Science顶刊发表": {
        "keywords": ["Nature", "Science", "Cell", "顶刊", "论文发表", "研究成果"],
        "patterns": [r"登Nature封面", r"登Science封面", r"Nature发表", r"Science发表"],
        "weight": 90,
    },
}

# A级选题：优先（高传播潜力）
A_LEVEL_TOPICS = {
    "科技巨头重大动态": {
        "keywords": [
            "OpenAI", "Anthropic", "Google", "Microsoft", "Meta", "苹果", "Apple", "英伟达", "NVIDIA",
            "黄仁勋", "Sam Altman", "奥特曼", "纳德拉", "扎克伯格",
        ],
        "weight": 85,
    },
    "国产大模型进展": {
        "keywords": [
            "字节", "豆包", "阿里", "通义", "百度", "文心", "腾讯", "混元", "智谱", "月之暗面",
            "Kimi", "MiniMax", "零一万物", "李开复", "王小川", "李志飞",
        ],
        "weight": 80,
    },
    "开源爆款项目": {
        "keywords": ["GitHub", "开源", "开源项目", "Star", "标星", "万星"],
        "patterns": [r"GitHub.*万.*星", r"GitHub.*热榜", r"开源.*代码"],
        "weight": 75,
    },
    "学术突破/首次": {
        "keywords": ["首次", "首个", "突破", "颠覆", "里程碑", "创纪录", "世界第一"],
        "patterns": [r"首次.*实现", r"首个.*诞生", r"突破.*纪录"],
        "weight": 75,
    },
    "人物励志故事": {
        "keywords": ["博士", "院士", "清华", "北大", "MIT", "斯坦福", "年薪", "offer", "天才少年", "逆袭"],
        "patterns": [r"年薪.*万", r"华为天才少年", r"复读.*考上", r"博士.*心路"],
        "weight": 70,
    },
    "社会/伦理争议": {
        "keywords": ["曝光", "揭秘", "内网", "控诉", "争议", "伦理", "走火入魔"],
        "patterns": [r".*曝光：", r"内网.*字", r"走火入魔"],
        "weight": 75,
    },
}

# B级选题：可选
B_LEVEL_TOPICS = {
    "产品评测/实测": {"keywords": ["评测", "实测", "体验", "上手", "测评", "对比"], "weight": 60},
    "技术深度解析": {"keywords": ["技术解析", "原理", "架构", "算法", "论文解读"], "weight": 55},
    "航天/太空": {"keywords": ["SpaceX", "火箭", "卫星", "空间站", "太空", "火星", "登月"], "weight": 70},
    "芯片/量子计算": {"keywords": ["芯片", "量子计算", "量子计算机", "GPU", "光刻机", "脑机接口"], "weight": 65},
}

# 降低权重的内容
REDUCE_WEIGHT_TOPICS = {
    "一般商业新闻": ["融资", "估值", "上市", "财报", "营收", "利润", "股价"],
    "消费电子": ["手机", "耳机", "平板", "手表", "可穿戴", "iPhone", "Samsung"],
    "常规汽车": ["电动车", "新能源汽车", "车型", "续航", "Model 3", "Model Y"],
}

# 热点人物监控列表
HOT_PEOPLE = [
    "马斯克", "Elon Musk", "黄仁勋", "Jensen Huang", "Sam Altman", "奥特曼",
    "稚晖君", "彭志辉", "王小川", "李志飞", "李开复", "张一鸣",
    "Demis Hassabis", "Satya Nadella", "Sundar Pichai", "Mark Zuckerberg",
]

# 热点公司监控列表
HOT_COMPANIES = [
    "OpenAI", "Anthropic", "xAI", "DeepMind", "Google", "Microsoft", "Meta", "Apple", "Amazon",
    "Nvidia", "NVIDIA", "Intel", "AMD", "Tesla", "SpaceX",
    "字节", "ByteDance", "抖音", "豆包", "阿里", "Alibaba", "百度", "Baidu",
    "腾讯", "Tencent", "华为", "Huawei", "智谱", "月之暗面", "Kimi",
]

# 高传播标题元素
HIGH_ENGAGEMENT_ELEMENTS = {
    "情绪词": ["炸裂", "炸场", "炸了", "王炸", "震撼", "颠覆", "疯狂", "太疯狂了"],
    "时效词": ["刚刚", "突发", "深夜", "凌晨"],
    "突破词": ["首次", "首个", "创造历史", "里程碑", "世界第一"],
    "互动词": ["网友", "网友：", "网友评价", "网友热议"],
    "权威背书": ["Nature", "Science", "顶刊", "院士", "博士"],
}


# ==================== 评分系统（0-100 标准化，含多源加分） ====================

def calculate_score(title, content, source_count=1):
    """计算新闻选题评分（满分100），返回 (score, level, reasons)

    Args:
        source_count: 报道该事件的来源数量，多源有额外加分
    """
    text = f"{title} {content}".lower()
    score = 0
    reasons = []

    # 1. S级选题检测
    for topic_name, cfg in S_LEVEL_TOPICS.items():
        for kw in cfg.get("keywords", []):
            if kw.lower() in text:
                score += cfg["weight"]
                reasons.append(f"S级-{topic_name}")
                break
        for pat in cfg.get("patterns", []):
            if re.search(pat, text, re.IGNORECASE):
                score += 10
                reasons.append(f"S级模式-{topic_name}")
                break

    # 2. A级选题检测
    for topic_name, cfg in A_LEVEL_TOPICS.items():
        for kw in cfg.get("keywords", []):
            if kw.lower() in text:
                score += cfg["weight"] // 2
                reasons.append(f"A级-{topic_name}")
                break

    # 3. 热点人物加分
    for person in HOT_PEOPLE:
        if person.lower() in text:
            score += 15
            reasons.append(f"热点人物-{person}")
            break

    # 4. 热点公司加分
    for company in HOT_COMPANIES:
        if company.lower() in text:
            score += 10
            reasons.append(f"热点公司-{company}")
            break

    # 5. 高传播元素加分
    for elem_type, elements in HIGH_ENGAGEMENT_ELEMENTS.items():
        for elem in elements:
            if elem in title:
                score += 5
                reasons.append(f"高传播-{elem}")
                break

    # 6. 时效性加分
    if any(w in title for w in ["刚刚", "突发", "深夜", "凌晨"]):
        score += 10
        reasons.append("时效性强")

    # 7. 多源报道加分（每多一个来源+5分，最高+20分）
    if source_count > 1:
        multi_source_bonus = min((source_count - 1) * 5, 20)
        score += multi_source_bonus
        reasons.append(f"多源报道(+{multi_source_bonus})")

    # 8. 降权扣分
    for topic_name, keywords in REDUCE_WEIGHT_TOPICS.items():
        for kw in keywords:
            if kw.lower() in text:
                score -= 20
                reasons.append(f"降权-{topic_name}")
                break

    score = max(0, min(100, score))
    if score >= 90:
        level = "S"
    elif score >= 75:
        level = "A"
    elif score >= 60:
        level = "B"
    else:
        level = "C"

    return score, level, list(set(reasons))


# ==================== 翻译映射（精简核心） ====================

TRANS_MAP = {
    # 公司/产品
    "openai": "OpenAI", "anthropic": "Anthropic", "claude": "Claude",
    "chatgpt": "ChatGPT", "gemini": "Gemini", "google": "Google",
    "deepmind": "DeepMind", "microsoft": "微软", "meta": "Meta",
    "apple": "苹果", "amazon": "亚马逊", "nvidia": "英伟达",
    "tesla": "特斯拉", "spacex": "SpaceX", "xai": "xAI",
    # 技术术语
    "artificial intelligence": "人工智能", "machine learning": "机器学习",
    "deep learning": "深度学习", "large language model": "大语言模型",
    "neural network": "神经网络", "computer vision": "计算机视觉",
    "natural language": "自然语言", "ai model": "AI模型",
    "ai agent": "AI智能体", "ai system": "AI系统",
    "quantum computing": "量子计算", "quantum computer": "量子计算机",
    "algorithm": "算法", "framework": "框架", "architecture": "架构",
    "infrastructure": "基础设施", "database": "数据库",
    "robot": "机器人", "robotics": "机器人技术",
    "autonomous": "自主", "automated": "自动化",
    "blockchain": "区块链", "supercomputer": "超级计算机",
    # 动作
    "launches": "发布", "launched": "发布", "launch": "发布",
    "releases": "推出", "released": "推出", "release": "推出",
    "announces": "宣布", "announced": "宣布",
    "introduces": "推出", "introduced": "推出",
    "develops": "开发", "developed": "开发",
    "achieves": "实现", "demonstrates": "展示",
    "outperforms": "优于", "beats": "击败",
    # 形容词
    "breakthrough": "突破", "milestone": "里程碑",
    "revolutionary": "革命性", "state-of-the-art": "最先进",
    "cutting-edge": "前沿", "novel": "新型", "innovative": "创新",
    "significantly": "显著", "dramatically": "大幅",
    # 科研
    "researchers": "研究人员", "scientists": "科学家",
    "published": "发表", "discovery": "发现", "findings": "发现",
    "experiment": "实验", "benchmark": "基准测试",
    "nature": "《自然》", "science": "《科学》",
    # 航天
    "rocket": "火箭", "satellite": "卫星", "spacecraft": "航天器",
    "starship": "星舰", "starlink": "星链", "nasa": "NASA",
    "astronaut": "宇航员", "mars": "火星", "moon": "月球", "orbit": "轨道",
    # 人事
    "ceo": "CEO", "cto": "CTO", "founder": "创始人",
    "co-founder": "联合创始人", "joins": "加入", "joined": "加入",
    "hired": "聘请", "appointed": "任命",
    "resigns": "辞职", "resigned": "辞职",
    # 医疗
    "medical": "医疗", "drug": "药物", "treatment": "治疗",
    "disease": "疾病", "cancer": "癌症", "gene": "基因",
    "protein": "蛋白质", "clinical": "临床",
    # 安全
    "safety": "安全", "security": "安全", "privacy": "隐私",
    "risk": "风险", "threat": "威胁", "concern": "担忧",
}

# 实体识别映射
ENTITY_KEYWORDS = [
    ("OpenAI", "OpenAI"), ("Anthropic", "Anthropic"), ("Claude", "Anthropic"),
    ("ChatGPT", "OpenAI"), ("GPT-4", "OpenAI"), ("Google", "Google"),
    ("DeepMind", "Google"), ("Gemini", "Google"), ("Microsoft", "微软"),
    ("xAI", "xAI"), ("Grok", "xAI"), ("Meta", "Meta"), ("Apple", "苹果"),
    ("Nvidia", "英伟达"), ("Tesla", "特斯拉"),
    ("SpaceX", "SpaceX"), ("Starship", "SpaceX"),
    ("Sam Altman", "Sam Altman"), ("Elon Musk", "马斯克"),
    ("Dario Amodei", "Dario Amodei"), ("Demis Hassabis", "Demis Hassabis"),
    ("Jensen Huang", "黄仁勋"),
]

# 类型检测关键词
TOPIC_TYPE_KEYWORDS = {
    "breakthrough": "突破", "milestone": "突破", "world first": "突破",
    "state-of-the-art": "突破", "首次": "突破", "颠覆": "突破",
    "launch": "新品", "release": "新品", "发布": "新品", "推出": "新品",
    "funding": "融资", "raised": "融资", "融资": "融资",
    "safety": "安全", "concern": "争议", "controversy": "争议", "争议": "争议",
    "joins": "人事", "hired": "人事", "appointed": "人事", "离职": "人事",
    "Nature": "科研", "Science": "科研", "论文": "科研", "研究": "科研",
}


# ==================== 工具函数 ====================

def clean_html(html_text):
    """清理 HTML 标签，提取纯文本"""
    if not html_text:
        return ""
    text = re.sub(r'<(script|style)[^>]*>[^<]*</\1>', ' ', html_text, flags=re.IGNORECASE)
    text = re.sub(r'<img[^>]*>', ' ', text, flags=re.IGNORECASE)
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'https?://\S+', '', text)
    return ' '.join(text.split()).strip()


def extract_article_content(url, timeout=10):
    """尝试抓取文章正文内容

    Returns:
        str: 提取的正文内容，失败返回空字符串
    """
    if not url:
        return ""

    try:
        # 使用 curl 获取页面内容
        cmd = [
            "curl", "-s", "-L",  # -L 跟随重定向
            "--connect-timeout", str(timeout),
            "--max-time", str(timeout * 2),
            "--socks5-hostname", PROXY.replace("socks5h://", ""),
            "-A", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "-k", url,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout * 2 + 5)

        if result.returncode != 0:
            return ""

        html = result.stdout
        if not html:
            return ""

        # 简单提取正文：移除 script/style，提取 p 标签内容
        # 移除 script 和 style
        text = re.sub(r'<(script|style|nav|header|footer|aside)[^>]*>.*?</\1>', ' ', html, flags=re.IGNORECASE | re.DOTALL)
        # 提取 p 标签内容
        paragraphs = re.findall(r'<p[^>]*>(.*?)</p>', text, flags=re.IGNORECASE | re.DOTALL)
        # 清理 HTML 标签
        content_parts = []
        for p in paragraphs[:5]:  # 取前5段
            clean = re.sub(r'<[^>]+>', ' ', p)
            clean = ' '.join(clean.split())
            if len(clean) > 30:  # 过滤太短的段落
                content_parts.append(clean)

        return ' '.join(content_parts)[:500]  # 限制长度

    except Exception as e:
        return ""


def detect_topic_type(title, content):
    """检测选题类型"""
    full_text = f"{title} {content}".lower()
    for keyword, topic_type in TOPIC_TYPE_KEYWORDS.items():
        if keyword.lower() in full_text:
            return topic_type
    return "科技"


def detect_entities(title, content):
    """识别文本中的实体"""
    full_text = f"{title} {content}"
    entities = []
    for keyword, entity in ENTITY_KEYWORDS:
        if keyword.lower() in full_text.lower() or keyword in title:
            if entity not in entities:
                entities.append(entity)
    return entities


def translate_phrase(phrase):
    """对英文短语进行关键词翻译"""
    result = phrase
    for en, cn in TRANS_MAP.items():
        result = re.sub(r'\b' + re.escape(en) + r'\b', cn, result, flags=re.IGNORECASE)
    return re.sub(r'\s+', ' ', result).strip()


# ==================== 量子位风格标题生成 ====================

def generate_quantum_bit_title(title, content, topic_type, entities):
    """生成量子位风格的纯中文标题（不带类型前缀）

    风格示例：
    - 效果炸裂！OpenAI首个视频生成模型发布，1分钟流畅高清
    - 刚刚，马斯克创造人类航天新壮举！空中炸毁火箭
    - 3个搞物理的颠覆了数学常识，数学天才陶哲轩：我开始压根不相信
    """
    text = f"{title} {content}".lower()
    main_entity = entities[0] if entities else ""

    # 清理原标题
    core = re.sub(r'^(RT|MT)\s*[@\w]+:\s*', '', title, flags=re.IGNORECASE)
    core = re.sub(r'https?://\S+', '', core)
    if " - " in core:
        core = core.split(" - ")[0]
    if " | " in core:
        core = core.split(" | ")[0]

    # 翻译核心内容
    cn_core = translate_phrase(core)

    # 根据内容类型选择标题模板

    # 模板1: AI/大模型发布 - 效果炸裂型
    if any(kw in text for kw in ["gpt", "claude", "gemini", "sora", "llama", "模型", "发布", "推出"]):
        if "视频" in text or "video" in text:
            return f"效果炸裂！{main_entity}首个视频生成模型发布，1分钟流畅高清"
        if "多模态" in text or "multimodal" in text:
            return f"效果炸裂！{main_entity}发布多模态大模型，图文音视频全搞定"
        if main_entity:
            return f"效果炸裂！{main_entity}发布新一代大模型，能力全面升级"
        return f"效果炸裂！{cn_core[:40]}"

    # 模板2: 马斯克/SpaceX - 刚刚创造历史型
    if "马斯克" in text or "musk" in text or "spacex" in text:
        if "发射" in text or "launch" in text:
            return f"刚刚，马斯克创造人类航天新壮举！星舰发射圆满成功"
        if "回收" in text or "landing" in text:
            return f"刚刚，马斯克再次创造历史！火箭回收技术取得新突破"
        return f"刚刚，马斯克{text[:20]}..."

    # 模板3: Nature/Science - 颠覆认知型
    if "nature" in text or "science" in text or "顶刊" in text:
        if "数学" in text:
            return f"颠覆认知！{cn_core[:35]}...，数学界震动"
        return f"颠覆认知！{cn_core[:40]}..."

    # 模板4: 人物/励志故事 - 网友热议型
    if "博士" in text or "院士" in text or "年薪" in text:
        if "华为" in text and "年薪" in text:
            return f"{cn_core[:40]}...，网友：这才是真正的天才"
        return f"{cn_core[:45]}...，网友热议"

    # 模板5: 开源/GitHub - 登顶热榜型
    if "github" in text or "开源" in text:
        return f"{cn_core[:35]}...，登顶GitHub热榜"

    # 模板6: 争议/爆料 - 曝光型
    if "曝光" in text or "揭秘" in text or "争议" in text:
        return f"{main_entity}{text[:25]}...曝光：{cn_core[30:60]}..."

    # 默认模板：直接翻译 + 情绪词
    if any(w in text for w in ["突破", "breakthrough", "首次", "first"]):
        return f"重大突破！{cn_core[:45]}..."

    # 简洁直接型
    return cn_core[:60]


def generate_summary_from_content(content, title, url, topic_type, entities):
    """生成摘要：优先抓取原文，失败则用模板

    Returns:
        str: 50-100字的中文摘要，或 "点击链接查看详情"
    """
    main_entity = entities[0] if entities else "该项目"

    # 尝试抓取原文
    if url:
        fetched_content = extract_article_content(url)
        if fetched_content:
            # 从抓取的内容中提取第一句完整的话
            sentences = re.split(r'[.!?。！？]\s+', fetched_content)
            for sent in sentences:
                sent = sent.strip()
                if len(sent) > 30 and len(sent) < 200:
                    # 翻译并清理
                    cn_sent = translate_phrase(sent)
                    cn_sent = re.sub(r'\s+', '', cn_sent)  # 移除空格
                    if len(cn_sent) >= 30:
                        return cn_sent[:100] if len(cn_sent) <= 100 else cn_sent[:97] + "..."

    # 降级：使用 Inoreader 摘要生成
    text = clean_html(content) if content else title
    if text:
        first_sent = text.split(".")[0] if "." in text else text[:150]
        cn_text = translate_phrase(first_sent.strip())
        cn_text = re.sub(r'\s+', '', cn_text)
        if len(cn_text) >= 20:
            templates = {
                "突破": f"{main_entity}在相关领域取得重要突破，展现了显著的技术进步",
                "新品": f"{main_entity}正式发布新产品，为行业带来新的解决方案",
                "融资": f"{main_entity}宣布获得融资，资金将用于业务扩张和技术研发",
                "人事": f"{main_entity}进行重要人事调整，此举将对公司发展产生重要影响",
                "争议": f"{main_entity}面临争议事件，引发业界广泛关注和讨论",
                "科研": f"{main_entity}的研究团队取得新进展，为相关领域提供重要参考",
                "安全": f"{main_entity}涉及安全问题，提醒行业关注相关风险",
            }
            summary = templates.get(topic_type, f"{main_entity}：{cn_text[:60]}")
            return summary[:100] if len(summary) <= 100 else summary[:97] + "..."

    # 最终降级
    return "点击链接查看详情"


# ==================== 多源聚合与去重 ====================

def calculate_similarity(s1, s2):
    """计算两个字符串的 Jaccard 相似度"""
    s1_lower, s2_lower = s1.lower(), s2.lower()
    if s1_lower in s2_lower or s2_lower in s1_lower:
        return 0.8

    stop_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'is', 'are', 'was', 'were'}

    def extract_kw(text):
        words = re.findall(r'\b\w{4,}\b', re.sub(r'[^\w\s]', ' ', text.lower()))
        return set(w for w in words if w not in stop_words)

    kw1, kw2 = extract_kw(s1), extract_kw(s2)
    if not kw1 or not kw2:
        return 0
    return len(kw1 & kw2) / len(kw1 | kw2)


def group_by_event(items):
    """按事件分组：相似标题归为同一事件

    Returns:
        list: 每个元素是 (representative_item, [similar_items]) 的元组
    """
    groups = []
    used = set()

    for i, item in enumerate(items):
        if i in used:
            continue

        group = [item]
        used.add(i)
        title1 = item["title"]

        for j, other in enumerate(items[i + 1:], i + 1):
            if j in used:
                continue
            title2 = other["title"]
            sim = calculate_similarity(title1, title2)
            if sim > 0.5:  # 相似度阈值
                group.append(other)
                used.add(j)

        groups.append(group)

    return groups


def merge_event_group(group):
    """合并同一事件的多个来源

    Returns:
        dict: 合并后的新闻条目
    """
    if not group:
        return None

    # 取评分最高的作为代表
    representative = max(group, key=lambda x: x.get("_score", 0))

    # 合并所有来源
    all_links = []
    seen_urls = set()
    seen_sources = set()

    for item in group:
        url = item.get("url", "")
        source = item.get("source", "Unknown")
        if url and url not in seen_urls:
            all_links.append({"name": source, "url": url})
            seen_urls.add(url)
            seen_sources.add(source)

    # 重新计算评分（含多源加分）
    score, level, reasons = calculate_score(
        representative["title"],
        representative.get("content", ""),
        source_count=len(all_links)
    )

    merged = {
        "title_en": representative["title"],
        "content": representative.get("content", ""),
        "url": representative.get("url", ""),
        "source": representative.get("source", "Unknown"),
        "published": representative.get("published", 0),
        "_score": score,
        "_level": level,
        "_reasons": reasons,
        "_sourceLinks": all_links,
        "_sourceCount": len(all_links),
    }

    return merged


# ==================== Inoreader API ====================

def curl_request(url, headers=None, timeout=30):
    """通过 curl + SOCKS5 代理发送请求"""
    cmd = [
        "curl", "-s",
        "--connect-timeout", str(timeout),
        "--max-time", str(timeout * 2),
        "--socks5-hostname", PROXY.replace("socks5h://", ""),
        "-k", url,
    ]
    if headers:
        for key, value in headers.items():
            cmd.extend(["-H", f"{key}: {value}"])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout


def get_token():
    """从本地配置读取 Inoreader access token"""
    config_path = os.path.expanduser("~/.openclaw/agents/main/agent/auth-profiles.json")
    with open(config_path) as f:
        config = json.load(f)
    return config.get("inoreader", {}).get("access_token")


def get_recent_items(token, hours=24, limit=200):
    """获取 Inoreader 最近 N 小时内容"""
    since = int(time.time()) - (hours * 3600)
    url = f"{INOREADER_API}/stream/contents/user/-/state/com.google/reading-list?n={limit}&ot={since}"
    response = curl_request(url, headers={"Authorization": f"Bearer {token}"})
    return json.loads(response)


def parse_items(data):
    """解析 Inoreader 返回的 items"""
    items = []
    for item in data.get("items", []):
        title = item.get("title", "")
        content = ""
        if "summary" in item and "content" in item["summary"]:
            content = item["summary"]["content"]
        elif "content" in item and isinstance(item["content"], dict):
            content = item["content"].get("content", "")
        content = re.sub(r'<[^>]+>', '', content)

        links = item.get("alternate", [])
        url = links[0].get("href", "") if links else ""
        source = item.get("origin", {}).get("title", "Unknown")

        items.append({
            "title": title,
            "content": content,
            "url": url,
            "source": source,
            "published": item.get("published", 0),
        })
    return items


# ==================== GitHub Pages 更新 ====================

def update_github_pages(news_data):
    """更新 news_data.json 并推送到 GitHub Pages"""
    try:
        today = datetime.now().strftime('%Y-%m-%d')
        data_file = "news_data.json"

        if os.path.exists(data_file):
            with open(data_file, 'r', encoding='utf-8') as f:
                archive = json.load(f)
        else:
            archive = {}

        archive[today] = news_data

        # 只保留最近 30 天
        dates = sorted(archive.keys())
        if len(dates) > 30:
            for old_date in dates[:-30]:
                del archive[old_date]

        with open(data_file, 'w', encoding='utf-8') as f:
            json.dump(archive, f, ensure_ascii=False, indent=2)

        print(f"[GitHub Pages] 数据已保存: {today}, {len(news_data)} 条新闻")

        # Git 提交推送
        env = os.environ.copy()
        env["GIT_AUTHOR_NAME"] = "OpenClaw Bot"
        env["GIT_AUTHOR_EMAIL"] = "bot@openclaw.ai"
        env["GIT_COMMITTER_NAME"] = "OpenClaw Bot"
        env["GIT_COMMITTER_EMAIL"] = "bot@openclaw.ai"

        subprocess.run(["git", "add", data_file], check=True, env=env)
        result = subprocess.run(
            ["git", "commit", "-m", f"Update news data for {today}"],
            capture_output=True, text=True, env=env,
        )

        if result.returncode == 0 or "nothing to commit" in (result.stdout + result.stderr).lower():
            push = subprocess.run(
                ["git", "push", "origin", "main"],
                capture_output=True, text=True, env=env,
            )
            if push.returncode == 0:
                print("[GitHub Pages] ✅ 推送成功")
                return True
            else:
                print(f"[GitHub Pages] ⚠️ 推送失败: {push.stderr}")
        else:
            print(f"[GitHub Pages] ⚠️ 提交失败: {result.stderr}")
        return False
    except Exception as e:
        print(f"[GitHub Pages] ❌ 更新出错: {e}")
        return False


# ==================== 主流程 ====================

def process_items(items):
    """处理流程：评分 → 多源聚合 → 生成中文标题/摘要"""

    # 第一步：初步评分
    scored_items = []
    for item in items:
        score, level, reasons = calculate_score(item["title"], item["content"])
        if score >= 60:  # 只保留 B 级及以上
            item["_score"] = score
            item["_level"] = level
            item["_reasons"] = reasons
            scored_items.append(item)

    print(f"初步筛选: {len(scored_items)} 条（评分≥60）")

    # 第二步：按事件分组（多源聚合）
    event_groups = group_by_event(scored_items)
    print(f"事件分组: {len(event_groups)} 个独立事件")

    # 第三步：合并每组并生成最终内容
    processed = []
    for group in event_groups:
        merged = merge_event_group(group)
        if not merged:
            continue

        # 生成中文标题（量子位风格，纯中文，无类型前缀）
        topic_type = detect_topic_type(merged["title_en"], merged["content"])
        entities = detect_entities(merged["title_en"], merged["content"])

        cn_title = generate_quantum_bit_title(
            merged["title_en"],
            merged["content"],
            topic_type,
            entities
        )

        # 生成摘要（优先抓取原文）
        summary = generate_summary_from_content(
            merged["content"],
            merged["title_en"],
            merged["url"],
            topic_type,
            entities
        )

        # 构建选题理由
        level_labels = {"S": "S级必报", "A": "A级优先", "B": "B级可选"}
        reason_text = f"【{level_labels.get(merged['_level'], merged['_level'])}】评分{merged['_score']}分"
        if merged["_sourceCount"] > 1:
            reason_text += f" | {merged['_sourceCount']}个来源报道"
        reason_text += f" | 命中：{', '.join(merged['_reasons'][:3])}"

        processed.append({
            "title": cn_title,
            "title_en": merged["title_en"],
            "summary": summary,
            "type": topic_type,
            "score": merged["_score"],
            "level": merged["_level"],
            "reason": reason_text,
            "url": merged["url"],
            "source": merged["source"],
            "sources": merged["_sourceCount"],
            "sourceLinks": merged["_sourceLinks"],
            "timestamp": int(time.time()),
        })

    # 按分数排序
    processed.sort(key=lambda x: x["score"], reverse=True)

    return processed


def main():
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始量子位风格新闻选题更新...")

    try:
        # 1. 获取 Token
        token = get_token()
        if not token:
            print("❌ 无法获取 Inoreader token")
            return

        # 2. 获取最近 24 小时内容
        print("获取最近 24 小时的内容...")
        data = get_recent_items(token, hours=24, limit=200)
        items = parse_items(data)
        print(f"获取到 {len(items)} 条内容")

        # 3. 评分、聚合、生成
        print("进行量子位风格评分与中文标题生成...")
        processed = process_items(items)
        print(f"筛选出 {len(processed)} 条高潜力选题（聚合后）")

        # 4. 更新 GitHub Pages
        if processed:
            print("\n[GitHub Pages] 开始更新...")
            update_github_pages(processed)
        else:
            print("没有高潜力新闻需要更新")

        # 5. 统计输出
        s_count = len([t for t in processed if t["level"] == "S"])
        a_count = len([t for t in processed if t["level"] == "A"])
        b_count = len([t for t in processed if t["level"] == "B"])
        multi_source = len([t for t in processed if t["sources"] > 1])

        print(f"\n✅ 完成!")
        print(f"\n选题统计:")
        print(f"  S级(必报): {s_count} 条")
        print(f"  A级(优先): {a_count} 条")
        print(f"  B级(可选): {b_count} 条")
        print(f"  多源报道: {multi_source} 条")

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
