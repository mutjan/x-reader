#!/usr/bin/env python3
"""
Inoreader 新闻更新脚本 - 每小时更新 GitHub Pages
Claude格式版本：生成中文标题和摘要，带reason字段
"""

import json
import subprocess
import os
import re
import openai
import socks
import socket
from datetime import datetime, timedelta
import time

INOREADER_API = "https://www.inoreader.com/reader/api/0"
PROXY = "socks5h://127.0.0.1:7890"
KIMI_API_KEY = "sk-kimi-JFYmtcth0yH8ibMkTBgjqBSHB7Srp2W7DR7YIa9XuPeR0AYIEbi90lsuanCdxF31"
KIMI_BASE_URL = "https://api.kimi.com/coding"

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


def setup_proxy():
    """设置 SOCKS5 代理并禁用 IPv6"""
    # 保存原始设置
    original_socket = socket.socket
    original_getaddrinfo = socket.getaddrinfo

    # 禁用 IPv6
    def getaddrinfo_ipv4_only(host, port, family=0, type=0, proto=0, flags=0):
        return original_getaddrinfo(host, port, socket.AF_INET, type, proto, flags)
    socket.getaddrinfo = getaddrinfo_ipv4_only

    # 设置 SOCKS5 代理
    socks.set_default_proxy(socks.SOCKS5, "127.0.0.1", 7890)
    socket.socket = socks.socksocket

    return original_socket, original_getaddrinfo


def restore_socket(original_socket, original_getaddrinfo):
    """恢复原始 socket 设置"""
    socket.socket = original_socket
    socket.getaddrinfo = original_getaddrinfo

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

    return text.strip()


def analyze_with_claude(items):
    """本地规则分析生成中文选题 - 标题和摘要都生成中文"""

    # 完整翻译映射表（在函数开头定义，供所有内部函数使用）
    trans_map = {
        # AI/技术
        'artificial intelligence': '人工智能',
        'machine learning': '机器学习',
        'deep learning': '深度学习',
        'large language model': '大语言模型',
        'neural network': '神经网络',
        'computer vision': '计算机视觉',
        'natural language': '自然语言',
        'ai model': 'AI模型',
        'ai system': 'AI系统',
        'ai tool': 'AI工具',
        'ai platform': 'AI平台',
        'chatbot': '聊天机器人',
        'spreadsheet': '电子表格',
        'database': '数据库',
        'algorithm': '算法',
        'framework': '框架',
        'architecture': '架构',
        'infrastructure': '基础设施',
        # 产品/公司
        'openai': 'OpenAI',
        'anthropic': 'Anthropic',
        'claude': 'Claude',
        'chatgpt': 'ChatGPT',
        'gpt-4': 'GPT-4',
        'gpt4': 'GPT-4',
        'gemini': 'Gemini',
        'google': 'Google',
        'deepmind': 'DeepMind',
        'microsoft': '微软',
        'meta': 'Meta',
        'apple': '苹果',
        'amazon': '亚马逊',
        'nvidia': '英伟达',
        'tesla': '特斯拉',
        'spacex': 'SpaceX',
        'xai': 'xAI',
        'grok': 'Grok',
        'qwen': '通义千问',
        'llama': 'Llama',
        'mistral': 'Mistral',
        # 动作
        'launches': '发布',
        'launched': '发布',
        'launch': '发布',
        'releases': '推出',
        'released': '推出',
        'release': '推出',
        'announces': '宣布',
        'announced': '宣布',
        'introduces': '推出',
        'introduced': '推出',
        'introducing': '推出',
        'unveils': ' unveiled',
        'unveiled': ' unveiled',
        'debuts': ' debut',
        'debuted': ' debut',
        'develops': '开发',
        'developed': '开发',
        'creates': '创建',
        'created': '创建',
        'builds': '构建',
        'built': '构建',
        'designs': '设计',
        'designed': '设计',
        'helps': '帮助',
        'helped': '帮助',
        'enables': '使能',
        'allows': '允许',
        'solves': '解决',
        'solved': '解决',
        'addresses': '解决',
        'tackles': '应对',
        'eliminates': '消除',
        'reduces': '减少',
        'improves': '改进',
        'enhances': '增强',
        'increases': '提高',
        'achieves': '实现',
        'demonstrates': '展示',
        'shows': '表明',
        'proves': '证明',
        'beats': '击败',
        'outperforms': '优于',
        'wins': '赢得',
        # 形容词/名词
        'new': '新',
        'novel': '新型',
        'innovative': '创新',
        'advanced': '先进',
        'breakthrough': '突破',
        'milestone': '里程碑',
        'revolutionary': '革命性',
        'state-of-the-art': '最先进',
        'cutting-edge': '前沿',
        'first': '首次',
        'world first': '世界首次',
        'global': '全球',
        'completely': '完全',
        'fully': '充分',
        'significantly': '显著',
        'dramatically': '大幅',
        'successfully': '成功',
        'faster': '更快',
        'better': '更好',
        'more': '更',
        'most': '最',
        # 技术名词
        'technology': '技术',
        'system': '系统',
        'platform': '平台',
        'model': '模型',
        'tool': '工具',
        'application': '应用',
        'solution': '解决方案',
        'method': '方法',
        'approach': '方法',
        'technique': '技术',
        'process': '过程',
        'service': '服务',
        'product': '产品',
        'feature': '功能',
        'capability': '能力',
        'function': '功能',
        'interface': '接口',
        'api': 'API',
        'software': '软件',
        'hardware': '硬件',
        'device': '设备',
        'chip': '芯片',
        'processor': '处理器',
        'gpu': 'GPU',
        'cloud': '云',
        'edge': '边缘',
        'on-device': '端侧',
        'real-time': '实时',
        'autonomous': '自主',
        'automated': '自动化',
        'intelligent': '智能',
        # 科研
        'research': '研究',
        'study': '研究',
        'paper': '论文',
        'article': '文章',
        'journal': '期刊',
        'publication': '发表',
        'published': '发表',
        'findings': '发现',
        'results': '结果',
        'discovery': '发现',
        'experiment': '实验',
        'trial': '试验',
        'test': '测试',
        'evaluation': '评估',
        'benchmark': '基准测试',
        'dataset': '数据集',
        'data': '数据',
        'analysis': '分析',
        'researchers': '研究人员',
        'scientists': '科学家',
        'team': '团队',
        'university': '大学',
        'institute': '研究所',
        'laboratory': '实验室',
        'nature': '《自然》',
        'science': '《科学》',
        'cell': '《细胞》',
        'arxiv': 'arXiv',
        # 医疗/生物
        'medical': '医疗',
        'medicine': '医学',
        'health': '健康',
        'healthcare': '医疗',
        'drug': '药物',
        'treatment': '治疗',
        'therapy': '疗法',
        'vaccine': '疫苗',
        'disease': '疾病',
        'cancer': '癌症',
        'tumor': '肿瘤',
        'cell': '细胞',
        'immune': '免疫',
        'gene': '基因',
        'genetic': '基因',
        'dna': 'DNA',
        'protein': '蛋白质',
        'clinical': '临床',
        'patient': '患者',
        'mice': '小鼠',
        'animal': '动物',
        'human': '人类',
        # 商业/融资
        'funding': '融资',
        'investment': '投资',
        'financing': '融资',
        'raises': '获得',
        'raised': '获得',
        'raise': '筹集',
        'million': '百万',
        'billion': '十亿',
        'dollars': '美元',
        'usd': '美元',
        'seed': '种子轮',
        'series': '轮',
        'round': '轮',
        'valuation': '估值',
        'revenue': '收入',
        'profit': '利润',
        'earnings': '收益',
        'ipo': 'IPO',
        'startup': '初创公司',
        'unicorn': '独角兽',
        'investor': '投资者',
        'venture': '风投',
        'capital': '资本',
        # 人事
        'ceo': 'CEO',
        'cto': 'CTO',
        'cfo': 'CFO',
        'chief': '首席',
        'executive': '执行官',
        'officer': '官',
        'president': '总裁',
        'vice': '副',
        'vp': 'VP',
        'head': '负责人',
        'lead': '领导',
        'leader': '领导者',
        'director': '总监',
        'manager': '经理',
        'founder': '创始人',
        'co-founder': '联合创始人',
        'joins': '加入',
        'joined': '加入',
        'hired': '聘请',
        'appointed': '任命',
        'named': '任命',
        'resigns': '辞职',
        'resigned': '辞职',
        'departs': '离职',
        'leaves': '离开',
        'exits': '退出',
        # 安全/争议
        'safety': '安全',
        'security': '安全',
        'privacy': '隐私',
        'risk': '风险',
        'threat': '威胁',
        'danger': '危险',
        'harm': '危害',
        'concern': '担忧',
        'issue': '问题',
        # 航天
        'space': '太空',
        'rocket': '火箭',
        'satellite': '卫星',
        'launch': '发射',
        'mission': '任务',
        'mars': '火星',
        'moon': '月球',
        'lunar': '月球',
        'orbit': '轨道',
        'spacecraft': '航天器',
        'spaceship': '飞船',
        'starship': '星舰',
        'falcon': '猎鹰',
        'dragon': '龙飞船',
        'starlink': '星链',
        'nasa': 'NASA',
        'astronaut': '宇航员',
        # 量子
        'quantum': '量子',
        'qubit': '量子比特',
        'quantum computing': '量子计算',
        'quantum computer': '量子计算机',
        'quantum processor': '量子处理器',
        'superposition': '叠加',
        'entanglement': '纠缠',
        'supremacy': '霸权',
        'advantage': '优势',
        # 其他
        'robot': '机器人',
        'robotics': '机器人技术',
        'automation': '自动化',
        'blockchain': '区块链',
        'crypto': '加密',
        'web3': 'Web3',
        '5g': '5G',
        '6g': '6G',
        'iot': '物联网',
        'big data': '大数据',
        'data center': '数据中心',
        'supercomputer': '超级计算机',
        'exascale': '百亿亿级',
    }

    # 选题评估关键词映射
    SCORE_RULES = {
        "breakthrough": 25, "milestone": 25, "world first": 25, "state-of-the-art": 20,
        "颠覆性": 25, "重大突破": 25, "里程碑": 25, "首次": 20, "创纪录": 20,
        "launch": 18, "release": 18, "announced": 15, "introducing": 18,
        "发布": 18, "推出": 18, "新品": 18, "上线": 15,
        "funding": 14, "raised": 14, "billion": 16, "valuation": 12,
        "融资": 14, "估值": 12, "亿美元": 16,
        "safety": 16, "concern": 14, "risk": 13, "controversy": 16, "scandal": 18,
        "争议": 16, "安全": 13, "风险": 13, "危机": 16,
        "joins": 16, "hired": 16, "appointed": 16, "ceo": 14, "chief": 14, "resign": 16,
        "离职": 16, "加入": 14, "任命": 14, "人事": 14,
        "OpenAI": 15, "Anthropic": 15, "Claude": 15, "ChatGPT": 15, "GPT-4": 15, "Gemini": 14,
        "xAI": 14, "DeepMind": 14, "Google": 10, "Microsoft": 10, "Apple": 10, "Meta": 10,
        "Sam Altman": 12, "Elon Musk": 12, "Dario Amodei": 12, "Demis Hassabis": 12,
        "马斯克": 12, "奥特曼": 12, "黄仁勋": 12,
        "Nature": 20, "Science": 20, "Cell": 20, "论文": 15, "研究": 12, "科研": 12,
        "SpaceX": 14, "Starship": 16, "火箭": 14, "航天": 12, "太空": 12,
        "quantum": 14, "量子": 14,
    }

    TOPIC_TYPES = {
        "breakthrough": "突破", "milestone": "突破", "world first": "突破", "state-of-the-art": "突破",
        "颠覆性": "突破", "重大突破": "突破", "里程碑": "突破", "首次": "突破",
        "launch": "新品", "release": "新品", "introducing": "新品", "发布": "新品", "推出": "新品",
        "funding": "融资", "raised": "融资", "融资": "融资", "估值": "融资",
        "safety": "安全", "concern": "争议", "risk": "安全", "controversy": "争议", "scandal": "争议",
        "争议": "争议", "安全": "安全", "风险": "安全", "危机": "争议",
        "joins": "人事", "hired": "人事", "appointed": "人事", "resign": "人事",
        "离职": "人事", "加入": "人事", "任命": "人事",
        "Nature": "科研", "Science": "科研", "Cell": "科研", "论文": "科研", "研究": "科研",
    }

    ENTITY_KEYWORDS = [
        ("OpenAI", "OpenAI"), ("Anthropic", "Anthropic"), ("Claude", "Anthropic"),
        ("ChatGPT", "OpenAI"), ("GPT-4", "OpenAI"), ("Google", "Google"),
        ("DeepMind", "Google"), ("Gemini", "Google"), ("Microsoft", "Microsoft"),
        ("xAI", "xAI"), ("Grok", "xAI"), ("Meta", "Meta"), ("Apple", "Apple"),
        ("Amazon", "Amazon"), ("Nvidia", "Nvidia"), ("Tesla", "Tesla"),
        ("SpaceX", "SpaceX"), ("Starship", "SpaceX"), ("Sam Altman", "Sam Altman"),
        ("Elon Musk", "Elon Musk"), ("Dario Amodei", "Dario Amodei"),
        ("Demis Hassabis", "Demis Hassabis"), ("Jensen Huang", "Jensen Huang"),
        ("阿里巴巴", "阿里巴巴"), ("阿里", "阿里巴巴"), ("Qwen", "阿里巴巴"),
        ("百度", "百度"), ("腾讯", "腾讯"), ("字节", "字节跳动"),
    ]

    # 中文标题模板映射
    CN_TITLE_TEMPLATES = {
        "breakthrough": "{entity}取得重大突破——{action}",
        "milestone": "{entity}达成重要里程碑——{action}",
        "launch": "{entity}发布{product}——{highlight}",
        "release": "{entity}推出{product}——{highlight}",
        "funding": "{entity}完成{amount}融资——{highlight}",
        "joins": "{person}加入{entity}——{highlight}",
        "hired": "{entity}任命{person}——{highlight}",
        "safety": "{entity}面临安全争议——{highlight}",
        "controversy": "{entity}陷入{topic}争议——{highlight}",
        "paper": "{entity}在{journal}发表论文——{highlight}",
        "default": "{entity}：{action}",
    }

    def generate_chinese_title(title, summary, topic_type, entities):
        """根据内容生成中文标题"""
        full_text = (title + " " + summary).lower()

        # 确定主要实体
        main_entity = entities[0] if entities else "科技"

        # 清理原标题
        clean_title = re.sub(r'^(RT|MT)\s*[@\w]+:\s*', '', title, flags=re.IGNORECASE)
        clean_title = re.sub(r'^[@\w]+:\s*', '', clean_title)
        clean_title = re.sub(r'https?://\S+', '', clean_title)
        clean_title = ' '.join(clean_title.split())

        # 截取核心标题（去掉来源等后缀）
        core_title = clean_title
        if " - " in core_title:
            core_title = core_title.split(" - ")[0]
        if " | " in core_title:
            core_title = core_title.split(" | ")[0]

        # 提取核心短语（前6-8个词）
        words = core_title.split()
        core_words = words[:8] if len(words) > 8 else words
        core_phrase = ' '.join(core_words)

        # 执行翻译
        cn_core = core_phrase
        for en, cn in trans_map.items():
            cn_core = re.sub(r'\b' + re.escape(en) + r'\b', cn, cn_core, flags=re.IGNORECASE)

        # 清理多余空格
        cn_core = re.sub(r'\s+', ' ', cn_core).strip()
        cn_core = cn_core[:45]  # 限制长度

        # 构建中文标题后缀
        suffix_map = {
            "突破": "取得重要突破",
            "新品": "正式发布",
            "融资": "获得资本青睐",
            "人事": "重要人事变动",
            "争议": "引发行业关注",
            "科研": "学术成果发布",
            "安全": "安全风险警示",
        }
        suffix = suffix_map.get(topic_type, "值得关注")

        return f"【{topic_type}】{main_entity}：{cn_core}——{suffix}"

    def generate_chinese_summary(summary, title, topic_type, entities, trans_map):
        """生成中文摘要"""
        # 清理文本
        text = clean_html(summary) if summary else title
        text = text[:300]  # 限制长度

        # 确定主要实体
        main_entity = entities[0] if entities else "该公司"

        # 提取关键句子（第一句）
        first_sent = text.split(".")[0] if "." in text else text[:150]
        first_sent = first_sent.strip()

        # 使用相同的翻译表进行翻译
        cn_text = first_sent
        for en, cn in trans_map.items():
            cn_text = re.sub(r'\b' + re.escape(en) + r'\b', cn, cn_text, flags=re.IGNORECASE)

        # 清理多余空格
        cn_text = re.sub(r'\s+', ' ', cn_text).strip()

        # 根据类型生成结构化摘要
        if topic_type == "突破":
            cn_summary = f"{main_entity}在{cn_text[:45]}方面取得重要突破，展现了显著的技术进步"
        elif topic_type == "新品":
            cn_summary = f"{main_entity}正式发布新产品，{cn_text[:45]}，为行业带来新的解决方案"
        elif topic_type == "融资":
            cn_summary = f"{main_entity}宣布获得融资，{cn_text[:45]}，资金将用于业务扩张和技术研发"
        elif topic_type == "人事":
            cn_summary = f"{main_entity}进行重要人事调整，{cn_text[:45]}，此举将对公司发展产生重要影响"
        elif topic_type == "争议":
            cn_summary = f"{main_entity}面临争议事件，{cn_text[:45]}，引发业界广泛关注和讨论"
        elif topic_type == "科研":
            cn_summary = f"{main_entity}的研究团队在{cn_text[:45]}方面取得新进展，为相关领域提供重要参考"
        elif topic_type == "安全":
            cn_summary = f"{main_entity}涉及安全问题，{cn_text[:45]}，提醒行业关注相关风险"
        else:
            cn_summary = f"{main_entity}：{cn_text[:60]}"

        # 限制长度
        if len(cn_summary) > 100:
            cn_summary = cn_summary[:97] + "..."

        return cn_summary

    topics = []

    for idx, item in enumerate(items):
        title = item.get("title", "")
        summary = item.get("summary", {}).get("content", "")
        full_text = f"{title} {summary}".lower()

        # 计算分数
        score = 0
        matched_keywords = []
        for keyword, points in SCORE_RULES.items():
            if keyword.lower() in full_text:
                score += points
                matched_keywords.append(keyword)

        # 只保留高分选题
        if score < 25:
            continue

        # 确定类型
        topic_type = "科技"
        for keyword, t in TOPIC_TYPES.items():
            if keyword.lower() in full_text:
                topic_type = t
                break

        # 确定实体
        entities = []
        for keyword, entity in ENTITY_KEYWORDS:
            if keyword.lower() in full_text or keyword in title:
                if entity not in entities:
                    entities.append(entity)
        entity_str = "|".join(entities[:2]) if entities else "科技"

        # 生成中文标题
        cn_title = generate_chinese_title(title, summary, topic_type, entities)

        # 生成中文摘要
        cn_summary = generate_chinese_summary(summary, title, topic_type, entities, trans_map)

        # 生成选题理由
        reason_keywords = [k for k in matched_keywords[:3]]
        reason = f"涉及{', '.join(reason_keywords)}等关键词，传播潜力高"

        topics.append({
            "title": cn_title,
            "summary": cn_summary,
            "type": topic_type,
            "entity": entity_str,
            "score": min(score, 100),
            "reason": reason,
            "source_ids": [idx + 1],
            "_item": item  # 保留原始item用于后续处理
        })

    # 按分数排序
    topics.sort(key=lambda x: x["score"], reverse=True)

    # 去重：相似标题合并
    merged_topics = []
    used = set()

    for i, t1 in enumerate(topics):
        if i in used:
            continue

        group = [t1]
        used.add(i)

        for j, t2 in enumerate(topics[i+1:], i+1):
            if j in used:
                continue

            # 计算相似度
            s1 = t1["title"].lower()
            s2 = t2["title"].lower()

            # 简单相似度检查
            def get_keywords(text):
                words = re.findall(r'\b\w{4,}\b', text)
                return set(words)

            kw1 = get_keywords(s1)
            kw2 = get_keywords(s2)

            if kw1 and kw2:
                intersection = len(kw1 & kw2)
                union = len(kw1 | kw2)
                similarity = intersection / union if union > 0 else 0
            else:
                similarity = 0

            # 如果相似度>0.5或包含相同实体+类型，合并
            if similarity > 0.5 or (t1["entity"] == t2["entity"] and t1["type"] == t2["type"] and similarity > 0.3):
                group.append(t2)
                used.add(j)

        # 合并组
        merged = group[0].copy()
        if len(group) > 1:
            merged["score"] = max(t["score"] for t in group)
            merged["source_ids"] = [sid for t in group for sid in t["source_ids"]]
            merged["reason"] += f"（合并{len(group)}条相似新闻）"
        del merged["_item"]
        merged_topics.append(merged)

    print(f"本地分析生成 {len(merged_topics)} 个选题")

    return {"topics": merged_topics}


def process_items(items):
    """处理条目 - 使用AI生成中文选题"""
    # 先筛选重要条目
    important_items = []
    for item in items:
        is_important, categories, score, title, summary = analyze_importance(item)
        if is_important:
            # 存储分析结果到item中供后续使用
            item['_categories'] = categories
            item['_score'] = score
            important_items.append(item)

    print(f"重要内容: {len(important_items)} 条")

    if not important_items:
        return []

    # 使用AI生成中文选题
    result = analyze_with_claude(important_items)
    topics = result.get("topics", [])

    if not topics:
        print("AI未生成任何选题")
        return []

    print(f"AI生成 {len(topics)} 个选题")

    # 将AI生成的选题与原始数据关联
    processed = []
    for t in topics:
        source_ids = t.get("source_ids", [])
        source_links = []
        seen_urls = set()

        # 收集来源链接
        for sid in source_ids:
            if 1 <= sid <= len(important_items):
                item = important_items[sid - 1]
                links = item.get("alternate", [])
                link = links[0].get("href", "") if links else ""
                origin = item.get("origin", {})
                source_name = origin.get("title", "未知来源")
                if link and link not in seen_urls:
                    source_links.append({"name": source_name, "url": link})
                    seen_urls.add(link)

        # 确定类型
        topic_type = t.get("type", "科技")
        type_mapping = {
            "突破": "hot", "新品": "hot", "争议": "hot",
            "融资": "business", "安全": "hot", "人事": "hot", "科研": "tech"
        }
        news_type = type_mapping.get(topic_type, "tech")

        # 获取最高分数
        max_score = max(
            important_items[sid - 1].get('_score', 0)
            for sid in source_ids if 1 <= sid <= len(important_items)
        ) if source_ids else 30

        processed.append({
            "title": t.get("title", ""),
            "summary": t.get("summary", ""),
            "type": news_type,
            "typeName": topic_type,
            "sources": len(source_links),
            "sourceLinks": source_links[:5],
            "categories": [topic_type] if topic_type else ["科技"],
            "score": t.get("score", max_score),
            "timestamp": int(time.time()),
            "reason": t.get("reason", "")
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
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 开始更新 Inoreader 新闻 (Claude格式)...")

    try:
        token = get_token()

        print("获取最近24小时的内容...")
        items = get_recent_items(token, hours=24, limit=200)

        print(f"获取到 {len(items.get('items', []))} 条内容")

        # process_items 现在使用AI生成中文选题并自动合并相似新闻
        processed = process_items(items.get("items", []))

        if processed:
            update_github_pages(processed)
        else:
            print("没有重要新闻需要更新")

        print(f"\n✅ 完成!")

    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
