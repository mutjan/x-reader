#!/usr/bin/env python3
"""
预告事件管理模块 v2.0
维护已预告事件列表，定期检查是否有新消息

改进点：
1. 关键词分级 - 区分核心关键词和辅助关键词
2. 内容相似度验证 - 防止错误匹配
3. 置信度评分 - 量化匹配质量

使用场景：
- No Priors 预告下期嘉宾是 Karpathy
- 某会议预告某大佬将发表演讲
- 产品发布预告

工作流程：
1. 添加预告事件到 upcoming_events.json
2. 每次执行新闻更新时，检查 RSS 内容是否匹配预告
3. 内容验证通过后，将事件从预告列表移除，加入正式选题
"""

import json
import os
import re
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

# 文件配置
UPCOMING_EVENTS_FILE = "upcoming_events.json"

# 默认空数据结构
DEFAULT_EVENTS_DATA = {
    "version": "2.0",
    "last_checked": None,
    "events": [],
    "zeitgeist": []  # 时代情绪 - 科技领域集体期待和情绪
}

# Zeitgeist 情绪趋势类型
ZEITGEIST_TRENDS = {
    "rising": "上升",      # 热度在增加
    "stable": "稳定",      # 热度平稳
    "declining": "下降",   # 热度在减退
    "cyclical": "周期性"   # 周期性出现
}

# Zeitgeist 情绪类别
ZEITGEIST_CATEGORIES = {
    "expectation": "期待",     # 等待某产品/技术
    "frustration": "焦虑",     # 对现状不满
    "nostalgia": "怀旧",       # 怀念过去
    "excitement": "兴奋",      # 对新事物兴奋
    "skepticism": "质疑",      # 对某事持怀疑态度
    "fomo": "错失恐惧"         # 害怕错过
}

# 辅助关键词列表 - 这些词单独匹配不能触发事件
cAUXILIARY_KEYWORDS = {
    'podcast', 'episode', 'interview', 'video', 'live', 'stream',
    'news', 'article', 'report', 'update', 'announcement',
    'release', 'launch', 'new', 'latest', 'breaking',
    'ai', 'artificial intelligence', 'machine learning', 'deep learning',
    'technology', 'tech', 'innovation', 'startup', 'company',
    'blog', 'post', 'story', 'feature', 'analysis',
    'review', 'guide', 'tutorial', 'explained', 'how to',
    'today', 'yesterday', 'this week', 'this month', '2026', '2025'
}


def load_upcoming_events():
    """加载预告事件列表"""
    if not os.path.exists(UPCOMING_EVENTS_FILE):
        return DEFAULT_EVENTS_DATA.copy()
    
    try:
        with open(UPCOMING_EVENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 确保必要字段存在
        if "events" not in data:
            data["events"] = []
        if "version" not in data:
            data["version"] = "1.0"
        return data
    except Exception as e:
        logger.error(f"[预告事件] 加载失败: {e}")
        return DEFAULT_EVENTS_DATA.copy()


def save_upcoming_events(data):
    """保存预告事件列表"""
    try:
        data["last_checked"] = datetime.now().isoformat()
        with open(UPCOMING_EVENTS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"[预告事件] 保存失败: {e}")
        return False


def classify_keywords(keywords):
    """
    将关键词分类为核心关键词和辅助关键词
    
    核心关键词：专有名词、人名、产品名、公司名等（必须匹配至少1个）
    辅助关键词：通用词、类别词等（仅用于提高置信度，不能单独触发）
    
    Returns:
        (core_keywords, auxiliary_keywords)
    """
    core_keywords = []
    auxiliary_keywords = []
    
    for kw in keywords:
        kw_lower = kw.lower().strip()
        
        # 判断是否为辅助词
        is_auxiliary = False
        
        # 1. 在辅助词列表中
        if kw_lower in cAUXILIARY_KEYWORDS:
            is_auxiliary = True
        
        # 2. 是常见的短词（小于5字符的英文词通常是辅助词）
        if len(kw_lower) <= 5 and kw_lower.isalpha():
            is_auxiliary = True
        
        # 3. 是时间相关词
        if kw_lower.isdigit() or re.match(r'^20\d{2}$', kw_lower):
            is_auxiliary = True
        
        if is_auxiliary:
            auxiliary_keywords.append(kw)
        else:
            core_keywords.append(kw)
    
    return core_keywords, auxiliary_keywords


def validate_content_similarity(event, item, matched_keywords):
    """
    验证内容相似度，防止错误匹配
    
    使用多种验证方法：
    1. 核心实体检查（人名、产品名是否出现）
    2. 标题相似度检查
    3. URL来源相关性检查
    
    Returns:
        (is_valid, confidence_score, reason)
    """
    title = item.get('title', '')
    content = item.get('content', '')
    text = f"{title} {content}".lower()
    url = item.get('url', '').lower()
    
    event_keywords = event.get("expected_keywords", [])
    core_keywords, auxiliary_keywords = classify_keywords(event_keywords)
    
    confidence = 0.0
    checks_passed = []
    
    # 检查1: 核心关键词匹配（必须）
    core_matches = sum(1 for k in core_keywords if k.lower() in text or k.lower() in url)
    if core_keywords:
        core_ratio = core_matches / len(core_keywords)
        confidence += core_ratio * 0.5  # 核心匹配占50%权重
        if core_matches >= 1:
            checks_passed.append(f"核心词匹配({core_matches}/{len(core_keywords)})")
    
    # 检查2: 标题相关性（事件标题和新闻标题的相似度）
    event_title = event['title'].lower()
    news_title = title.lower()
    
    # 提取有意义的词（去除常见词）
    common_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 
                    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will',
                    'would', 'could', 'should', 'may', 'might', 'must', 'shall',
                    'can', 'need', 'dare', 'ought', 'used', 'to', 'of', 'in',
                    'for', 'on', 'with', 'at', 'by', 'from', 'as', 'into',
                    'through', 'during', 'before', 'after', 'above', 'below',
                    'between', 'under', 'and', 'but', 'or', 'yet', 'so',
                    'if', 'because', 'although', 'though', 'while', 'where',
                    'when', 'that', 'which', 'who', 'whom', 'whose', 'what',
                    'this', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
                    'we', 'they', 'me', 'him', 'her', 'us', 'them'}
    
    event_title_words = set(w for w in re.findall(r'\b\w+\b', event_title) if w not in common_words and len(w) > 2)
    news_title_words = set(w for w in re.findall(r'\b\w+\b', news_title) if w not in common_words and len(w) > 2)
    
    if event_title_words and news_title_words:
        title_overlap = len(event_title_words & news_title_words) / len(event_title_words | news_title_words)
        confidence += title_overlap * 0.2
        if title_overlap > 0.1:
            checks_passed.append(f"标题相关({title_overlap:.2f})")
    
    # 检查3: URL 来源相关性
    source_hint = event.get('source_hint', '').lower()
    if source_hint and source_hint in url:
        confidence += 0.15
        checks_passed.append("来源匹配")
    
    # 检查4: 辅助关键词匹配
    aux_matches = sum(1 for k in auxiliary_keywords if k.lower() in text)
    if auxiliary_keywords:
        aux_ratio = aux_matches / len(auxiliary_keywords)
        confidence += aux_ratio * 0.15
        if aux_matches >= 1:
            checks_passed.append(f"辅助词匹配({aux_matches})")
    
    # 验证规则：
    # - 必须匹配至少 1 个核心关键词（如果有核心关键词的话）
    # - 置信度 >= 0.6 视为有效匹配
    # - 如果只匹配辅助关键词，即使数量多也无效
    
    is_valid = False
    reason = ""
    
    # 强制要求：如果有核心关键词，必须匹配至少1个
    if len(core_keywords) > 0 and core_matches == 0:
        is_valid = False
        reason = f"缺少核心关键词匹配 (核心词: {core_keywords}, 匹配到的: {matched_keywords})"
    elif confidence >= 0.6:
        is_valid = True
        reason = f"高置信度匹配: {', '.join(checks_passed)}"
    elif confidence >= 0.4 and core_matches >= 1:
        is_valid = True  # 低置信度但有关键核心匹配，允许通过但记录
        reason = f"中等置信度匹配: {', '.join(checks_passed)} (建议复核)"
    else:
        is_valid = False
        reason = f"置信度不足 ({confidence:.2f}): 仅匹配 {matched_keywords}"
    
    return is_valid, confidence, reason


def check_item_against_events(item):
    """
    检查单条新闻是否匹配任何预告事件（改进版，带关键词分级和内容验证）
    
    Returns:
        (matched_event_id, match_details) 或 (None, None)
    """
    data = load_upcoming_events()
    pending_events = [e for e in data["events"] if e["status"] == "pending"]
    
    if not pending_events:
        return None, None
    
    text = f"{item.get('title', '')} {item.get('content', '')}".lower()
    url = item.get('url', '').lower()
    
    for event in pending_events:
        keywords = event.get("expected_keywords", [])
        if not keywords:
            continue
        
        # 分类关键词
        core_keywords, auxiliary_keywords = classify_keywords(keywords)
        
        # 收集匹配的关键词
        matched_keywords = []
        core_matches = 0
        aux_matches = 0
        
        for keyword in keywords:
            keyword_lower = keyword.lower()
            if keyword_lower in text or keyword_lower in url:
                matched_keywords.append(keyword)
                if keyword in core_keywords:
                    core_matches += 1
                else:
                    aux_matches += 1
        
        # 快速过滤：至少匹配 1 个关键词才继续
        if len(matched_keywords) == 0:
            continue
        
        # 如果只匹配了辅助关键词，直接跳过（避免 peptides 文章匹配到 podcast+episode 的情况）
        if core_matches == 0 and len(core_keywords) > 0:
            logger.debug(f"[预告事件] 仅匹配辅助关键词，跳过: {item.get('title', '')[:50]}...")
            logger.debug(f"  核心词: {core_keywords}, 辅助词: {auxiliary_keywords}, 匹配到: {matched_keywords}")
            continue
        
        # 内容相似度验证
        is_valid, confidence, reason = validate_content_similarity(
            event, item, matched_keywords
        )
        
        if is_valid:
            match_details = {
                "event_id": event["id"],
                "event_title": event["title"],
                "matched_keywords": matched_keywords,
                "core_matches": core_matches,
                "aux_matches": aux_matches,
                "match_score": confidence,
                "validation_reason": reason
            }
            
            if confidence < 0.6:
                logger.warning(f"[预告事件] 低置信度匹配 ({confidence:.2f}): {item.get('title', '')[:50]}...")
                logger.warning(f"  原因: {reason}")
            else:
                logger.info(f"[预告事件] 匹配成功 ({confidence:.2f}): {event['title'][:50]}...")
                logger.info(f"  验证: {reason}")
            
            return event["id"], match_details
        else:
            # 记录被拒绝的匹配（用于调试）
            if len(matched_keywords) >= 2:
                logger.debug(f"[预告事件] 匹配被拒绝: {item.get('title', '')[:50]}...")
                logger.debug(f"  原因: {reason}")
    
    return None, None


def check_items_against_events(items):
    """
    批量检查新闻列表，返回匹配的事件和新闻
    
    Returns:
        {
            "matched": [(event, news_item, match_details), ...],
            "unmatched": [item, ...]
        }
    """
    matched = []
    unmatched = []
    
    # 跟踪已匹配的事件ID，避免重复匹配
    matched_event_ids = set()
    
    for item in items:
        event_id, match_details = check_item_against_events(item)
        
        if event_id and event_id not in matched_event_ids:
            # 加载完整事件信息
            data = load_upcoming_events()
            event = next((e for e in data["events"] if e["id"] == event_id), None)
            
            if event:
                matched.append((event, item, match_details))
                matched_event_ids.add(event_id)
        else:
            unmatched.append(item)
    
    return {"matched": matched, "unmatched": unmatched}


def add_upcoming_event(title, description, expected_keywords, source_hint="", 
                       expected_date=None, priority="A"):
    """
    添加新的预告事件
    
    Args:
        title: 事件标题（如 "No Priors 预告：Karpathy 将做客下期节目"）
        description: 事件描述
        expected_keywords: 用于匹配的关键词列表（如 ["No Priors", "Karpathy", "podcast"]）
        source_hint: 来源提示（如 "No Priors 播客"）
        expected_date: 预计发布时间（ISO格式，可选）
        priority: 预期优先级（S/A+/A/B）
    """
    data = load_upcoming_events()
    
    # 生成唯一ID
    event_id = f"evt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(data['events'])}"
    
    event = {
        "id": event_id,
        "title": title,
        "description": description,
        "expected_keywords": expected_keywords if isinstance(expected_keywords, list) else [expected_keywords],
        "source_hint": source_hint,
        "expected_date": expected_date,
        "priority": priority,
        "created_at": datetime.now().isoformat(),
        "status": "pending",  # pending, found, expired
        "found_news": None,  # 找到后填入新闻数据
        "check_count": 0  # 检查次数
    }
    
    data["events"].append(event)
    save_upcoming_events(data)
    
    # 分类提示
    core, auxiliary = classify_keywords(expected_keywords)
    logger.info(f"[预告事件] 已添加: {title} (ID: {event_id})")
    logger.info(f"  核心关键词: {core}")
    logger.info(f"  辅助关键词: {auxiliary}")
    
    return event_id


def remove_upcoming_event(event_id):
    """移除预告事件"""
    data = load_upcoming_events()
    original_count = len(data["events"])
    data["events"] = [e for e in data["events"] if e["id"] != event_id]
    
    if len(data["events"]) < original_count:
        save_upcoming_events(data)
        logger.info(f"[预告事件] 已移除: {event_id}")
        return True
    return False


def update_event_status(event_id, status, found_news=None):
    """更新事件状态"""
    data = load_upcoming_events()
    
    for event in data["events"]:
        if event["id"] == event_id:
            event["status"] = status
            if found_news:
                event["found_news"] = found_news
            save_upcoming_events(data)
            return True
    
    return False


def convert_matched_to_news(event, item, match_details):
    """
    将匹配的预告事件转换为正式新闻格式
    
    Returns:
        符合 news_data.json 格式的新闻条目
    """
    from update_news import generate_version
    
    # 预告事件落地直接评为 S 级
    level = "S"
    final_score = 95
    
    # 添加置信度信息到 reason
    confidence = match_details.get("match_score", 0)
    validation_reason = match_details.get("validation_reason", "")
    
    news_item = {
        "title": f"【预告落地】{item.get('title', event['title'])}",
        "title_en": item.get("title", ""),
        "summary": f"此前预告的事件已发布。{item.get('content', event['description'])[:150]}...",
        "score": int(final_score),
        "level": level,
        "rating": level,
        "reason": f"【{level}级】评分{int(final_score)}分 | 预告事件落地: {event['title']} | 匹配: {validation_reason} | 关键词: {', '.join(match_details.get('matched_keywords', []))}",
        "entities": event.get("expected_keywords", [])[:5],
        "tags": ["预告落地", event.get("source_hint", "")],
        "url": item.get("url", ""),
        "source": item.get("source", "Unknown"),
        "sources": 1,
        "sourceLinks": [{"name": item.get("source", "Unknown"), "url": item.get("url", "")}],
        "timestamp": int(datetime.now().timestamp()),
        "version": generate_version() if 'generate_version' in dir() else datetime.now().strftime('%Y.%m.%d-001'),
        "is_upcoming_event": True,
        "upcoming_event_id": event["id"],
        "upcoming_event_source": event.get("source_hint", "")
    }
    
    return news_item


def get_pending_events_summary():
    """获取待处理预告事件摘要"""
    data = load_upcoming_events()
    pending = [e for e in data["events"] if e["status"] == "pending"]
    
    # 为每个事件添加关键词分类
    pending_with_classification = []
    for e in pending:
        core, auxiliary = classify_keywords(e.get("expected_keywords", []))
        pending_with_classification.append({
            "id": e["id"],
            "title": e["title"],
            "source_hint": e.get("source_hint", ""),
            "core_keywords": core,
            "auxiliary_keywords": auxiliary,
            "created_at": e["created_at"]
        })
    
    return {
        "total": len(data["events"]),
        "pending": len(pending),
        "found": len([e for e in data["events"] if e["status"] == "found"]),
        "expired": len([e for e in data["events"] if e["status"] == "expired"]),
        "pending_list": pending_with_classification
    }


def cleanup_expired_events(days=30):
    """清理过期的预告事件"""
    data = load_upcoming_events()
    cutoff = datetime.now() - timedelta(days=days)

    original_count = len(data["events"])

    # 保留：pending 状态 或 30天内的 found/expired
    filtered_events = []
    for event in data["events"]:
        if event["status"] == "pending":
            filtered_events.append(event)
        else:
            created = datetime.fromisoformat(event["created_at"])
            if created > cutoff:
                filtered_events.append(event)

    data["events"] = filtered_events
    save_upcoming_events(data)

    removed = original_count - len(filtered_events)
    if removed > 0:
        logger.info(f"[预告事件] 清理了 {removed} 条过期事件")

    return removed


# ==================== Zeitgeist (时代情绪) 管理 ====================

def load_zeitgeist():
    """加载时代情绪列表"""
    data = load_upcoming_events()
    return data.get("zeitgeist", [])


def save_zeitgeist(zeitgeist_list):
    """保存时代情绪列表"""
    data = load_upcoming_events()
    data["zeitgeist"] = zeitgeist_list
    save_upcoming_events(data)


def add_zeitgeist(topic, description, category="expectation", keywords=None,
                  heat_score=70, trend="rising", related_entities=None):
    """
    添加新的时代情绪

    Args:
        topic: 情绪主题（如 "内存降价期待"、"DeepSeek新品等待"）
        description: 情绪描述，说明这种情绪的背景和表现
        category: 情绪类别 (expectation/frustration/nostalgia/excitement/skepticism/fomo)
        keywords: 用于追踪的相关关键词列表
        heat_score: 热度评分 (0-100)
        trend: 趋势 (rising/stable/declining/cyclical)
        related_entities: 相关实体（公司、产品、技术等）

    Returns:
        zeitgeist_id: 新创建的情绪ID
    """
    zeitgeist_list = load_zeitgeist()

    # 检查是否已存在相同主题
    for z in zeitgeist_list:
        if z["topic"] == topic and z["status"] == "active":
            logger.warning(f"[Zeitgeist] 主题已存在: {topic}")
            return z["id"]

    # 生成唯一ID
    zeitgeist_id = f"zgt_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(zeitgeist_list)}"

    zeitgeist_item = {
        "id": zeitgeist_id,
        "topic": topic,
        "description": description,
        "category": category,
        "category_name": ZEITGEIST_CATEGORIES.get(category, "其他"),
        "keywords": keywords or [],
        "heat_score": heat_score,
        "trend": trend,
        "trend_name": ZEITGEIST_TRENDS.get(trend, "未知"),
        "related_entities": related_entities or [],
        "created_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
        "status": "active",  # active, faded, realized
        "mentions_count": 0,  # 提及次数统计
        "history": [  # 热度历史
            {"date": datetime.now().isoformat(), "score": heat_score, "note": "创建"}
        ]
    }

    zeitgeist_list.append(zeitgeist_item)
    save_zeitgeist(zeitgeist_list)

    logger.info(f"[Zeitgeist] 已添加: {topic} (ID: {zeitgeist_id})")
    logger.info(f"  类别: {ZEITGEIST_CATEGORIES.get(category, '其他')}")
    logger.info(f"  热度: {heat_score}/100, 趋势: {ZEITGEIST_TRENDS.get(trend, '未知')}")

    return zeitgeist_id


def update_zeitgeist_heat(zeitgeist_id, new_score, note=""):
    """更新时代情绪热度"""
    zeitgeist_list = load_zeitgeist()

    for z in zeitgeist_list:
        if z["id"] == zeitgeist_id:
            old_score = z["heat_score"]
            z["heat_score"] = new_score
            z["updated_at"] = datetime.now().isoformat()
            z["history"].append({
                "date": datetime.now().isoformat(),
                "score": new_score,
                "note": note or f"热度更新: {old_score} -> {new_score}"
            })

            # 自动判断趋势
            if new_score > old_score + 10:
                z["trend"] = "rising"
                z["trend_name"] = "上升"
            elif new_score < old_score - 10:
                z["trend"] = "declining"
                z["trend_name"] = "下降"
            else:
                z["trend"] = "stable"
                z["trend_name"] = "稳定"

            save_zeitgeist(zeitgeist_list)
            logger.info(f"[Zeitgeist] 热度更新: {z['topic']} {old_score} -> {new_score}")
            return True

    return False


def update_zeitgeist_status(zeitgeist_id, status, note=""):
    """
    更新时代情绪状态

    status:
    - active: 活跃中
    - faded: 已消退
    - realized: 已实现（如期待的产品发布了）
    """
    zeitgeist_list = load_zeitgeist()

    for z in zeitgeist_list:
        if z["id"] == zeitgeist_id:
            z["status"] = status
            z["updated_at"] = datetime.now().isoformat()
            if note:
                z["history"].append({
                    "date": datetime.now().isoformat(),
                    "score": z["heat_score"],
                    "note": note
                })
            save_zeitgeist(zeitgeist_list)
            logger.info(f"[Zeitgeist] 状态更新: {z['topic']} -> {status}")
            return True

    return False


def increment_zeitgeist_mentions(zeitgeist_id):
    """增加提及次数"""
    zeitgeist_list = load_zeitgeist()

    for z in zeitgeist_list:
        if z["id"] == zeitgeist_id:
            z["mentions_count"] = z.get("mentions_count", 0) + 1
            z["updated_at"] = datetime.now().isoformat()
            save_zeitgeist(zeitgeist_list)
            return True

    return False


def get_active_zeitgeist(min_heat=50):
    """获取活跃的时代情绪列表"""
    zeitgeist_list = load_zeitgeist()
    active = [z for z in zeitgeist_list
              if z["status"] == "active" and z["heat_score"] >= min_heat]
    # 按热度排序
    active.sort(key=lambda x: x["heat_score"], reverse=True)
    return active


def get_zeitgeist_summary():
    """获取时代情绪统计摘要"""
    zeitgeist_list = load_zeitgeist()

    active = [z for z in zeitgeist_list if z["status"] == "active"]
    faded = [z for z in zeitgeist_list if z["status"] == "faded"]
    realized = [z for z in zeitgeist_list if z["status"] == "realized"]

    # 按类别分组
    by_category = {}
    for z in active:
        cat = z.get("category_name", "其他")
        by_category.setdefault(cat, []).append(z)

    # 按趋势分组
    by_trend = {"上升": [], "稳定": [], "下降": [], "周期性": []}
    for z in active:
        trend = z.get("trend_name", "未知")
        if trend in by_trend:
            by_trend[trend].append(z)

    return {
        "total": len(zeitgeist_list),
        "active": len(active),
        "faded": len(faded),
        "realized": len(realized),
        "by_category": {k: len(v) for k, v in by_category.items()},
        "by_trend": {k: len(v) for k, v in by_trend.items()},
        "top_heat": active[:5] if active else [],
        "rising": by_trend["上升"][:3] if by_trend["上升"] else []
    }


def convert_zeitgeist_to_news(zeitgeist_item, news_title="", news_url=""):
    """
    将时代情绪转换为新闻格式（当情绪成为新闻时）
    例如："DeepSeek新品发布"实现了"等待DeepSeek新品"的情绪
    """
    from update_news import generate_version

    topic = zeitgeist_item["topic"]
    description = zeitgeist_item["description"]
    category_name = zeitgeist_item.get("category_name", "情绪")

    news_item = {
        "title": f"【时代情绪落地】{news_title or f'{topic}成为现实'}",
        "title_en": "",
        "summary": f"此前广泛关注的集体情绪已落地。{description[:150]}...",
        "score": 85,
        "level": "A+",
        "rating": "A+",
        "reason": f"【A+级】时代情绪落地: {topic} | 此前热度: {zeitgeist_item['heat_score']}/100 | 反映了科技圈的集体期待",
        "entities": zeitgeist_item.get("related_entities", []),
        "tags": ["时代情绪", category_name, "集体心理"],
        "url": news_url or "",
        "source": "Zeitgeist追踪",
        "sources": 1,
        "sourceLinks": [{"name": "Zeitgeist追踪", "url": news_url or ""}],
        "timestamp": int(datetime.now().timestamp()),
        "version": generate_version() if 'generate_version' in dir() else datetime.now().strftime('%Y.%m.%d-001'),
        "is_zeitgeist_realized": True,
        "zeitgeist_id": zeitgeist_item["id"],
        "zeitgeist_topic": topic
    }

    return news_item


def check_news_against_zeitgeist(news_item):
    """
    检查新闻是否与某个时代情绪相关
    如果相关，增加该情绪的提及次数，并可能触发情绪状态变更

    Returns:
        list of matched zeitgeist ids
    """
    zeitgeist_list = load_zeitgeist()
    matched_ids = []

    title = news_item.get("title", "").lower()
    content = news_item.get("content", "").lower()
    text = f"{title} {content}"

    for z in zeitgeist_list:
        if z["status"] != "active":
            continue

        # 检查关键词匹配
        keywords = z.get("keywords", [])
        match_count = sum(1 for kw in keywords if kw.lower() in text)

        if match_count >= 2:  # 至少匹配2个关键词
            increment_zeitgeist_mentions(z["id"])
            matched_ids.append(z["id"])
            logger.info(f"[Zeitgeist] 新闻匹配情绪: {z['topic']} (匹配 {match_count} 个关键词)")

    return matched_ids


# CLI 接口
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="预告事件管理工具")
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # 添加事件
    add_parser = subparsers.add_parser("add", help="添加预告事件")
    add_parser.add_argument("--title", required=True, help="事件标题")
    add_parser.add_argument("--description", default="", help="事件描述")
    add_parser.add_argument("--keywords", required=True, help="匹配关键词（逗号分隔）")
    add_parser.add_argument("--source", default="", help="来源提示")
    add_parser.add_argument("--date", default="", help="预计日期（YYYY-MM-DD）")
    add_parser.add_argument("--priority", default="A", choices=["S", "A+", "A", "B"], help="预期优先级")
    
    # 列出事件
    list_parser = subparsers.add_parser("list", help="列出所有预告事件")
    list_parser.add_argument("--status", default="pending", choices=["all", "pending", "found", "expired"], help="筛选状态")
    
    # 移除事件
    remove_parser = subparsers.add_parser("remove", help="移除预告事件")
    remove_parser.add_argument("event_id", help="事件ID")
    
    # 清理过期
    cleanup_parser = subparsers.add_parser("cleanup", help="清理过期事件")
    cleanup_parser.add_argument("--days", type=int, default=30, help="过期天数")

    # 测试匹配
    test_parser = subparsers.add_parser("test", help="测试匹配逻辑")
    test_parser.add_argument("--title", required=True, help="新闻标题")
    test_parser.add_argument("--content", default="", help="新闻内容")
    test_parser.add_argument("--url", default="", help="新闻URL")

    # Zeitgeist 子命令
    zgt_parser = subparsers.add_parser("zeitgeist", help="时代情绪管理")
    zgt_subparsers = zgt_parser.add_subparsers(dest="zgt_command", help="Zeitgeist 命令")

    # 添加时代情绪
    zgt_add = zgt_subparsers.add_parser("add", help="添加时代情绪")
    zgt_add.add_argument("--topic", required=True, help="情绪主题")
    zgt_add.add_argument("--description", required=True, help="情绪描述")
    zgt_add.add_argument("--category", default="expectation",
                         choices=list(ZEITGEIST_CATEGORIES.keys()),
                         help="情绪类别")
    zgt_add.add_argument("--keywords", required=True, help="关键词（逗号分隔）")
    zgt_add.add_argument("--heat", type=int, default=70, help="热度评分(0-100)")
    zgt_add.add_argument("--trend", default="rising",
                         choices=list(ZEITGEIST_TRENDS.keys()),
                         help="趋势")
    zgt_add.add_argument("--entities", default="", help="相关实体（逗号分隔）")

    # 列出时代情绪
    zgt_list = zgt_subparsers.add_parser("list", help="列出时代情绪")
    zgt_list.add_argument("--status", default="active",
                          choices=["all", "active", "faded", "realized"],
                          help="筛选状态")
    zgt_list.add_argument("--min-heat", type=int, default=0, help="最小热度")

    # 更新热度
    zgt_heat = zgt_subparsers.add_parser("heat", help="更新热度")
    zgt_heat.add_argument("id", help="情绪ID")
    zgt_heat.add_argument("score", type=int, help="新热度评分")
    zgt_heat.add_argument("--note", default="", help="备注")

    # 更新状态
    zgt_status = zgt_subparsers.add_parser("status", help="更新状态")
    zgt_status.add_argument("id", help="情绪ID")
    zgt_status.add_argument("status", choices=["active", "faded", "realized"],
                            help="新状态")
    zgt_status.add_argument("--note", default="", help="备注")

    # 统计摘要
    zgt_summary = zgt_subparsers.add_parser("summary", help="统计摘要")

    args = parser.parse_args()

    if args.command == "add":
        keywords = [k.strip() for k in args.keywords.split(",")]
        event_id = add_upcoming_event(
            title=args.title,
            description=args.description,
            expected_keywords=keywords,
            source_hint=args.source,
            expected_date=args.date if args.date else None,
            priority=args.priority
        )
        print(f"✅ 已添加预告事件: {event_id}")
    
    elif args.command == "list":
        data = load_upcoming_events()
        events = data["events"]
        if args.status != "all":
            events = [e for e in events if e["status"] == args.status]
        
        print(f"\n📋 预告事件列表 ({len(events)} 条)\n")
        for e in events:
            core, auxiliary = classify_keywords(e.get("expected_keywords", []))
            print(f"ID: {e['id']}")
            print(f"  标题: {e['title']}")
            print(f"  状态: {e['status']}")
            print(f"  核心关键词: {', '.join(core)}")
            print(f"  辅助关键词: {', '.join(auxiliary)}")
            print(f"  来源: {e.get('source_hint', '-')}")
            print(f"  创建时间: {e['created_at']}")
            print()
    
    elif args.command == "remove":
        if remove_upcoming_event(args.event_id):
            print(f"✅ 已移除事件: {args.event_id}")
        else:
            print(f"❌ 未找到事件: {args.event_id}")
    
    elif args.command == "cleanup":
        removed = cleanup_expired_events(args.days)
        print(f"✅ 清理了 {removed} 条过期事件")
    
    elif args.command == "test":
        # 创建测试新闻项
        test_item = {
            "title": args.title,
            "content": args.content,
            "url": args.url,
            "source": "Test"
        }
        
        print(f"\n🧪 测试匹配: {args.title}\n")
        
        event_id, match_details = check_item_against_events(test_item)
        
        if event_id:
            print(f"✅ 匹配成功!")
            print(f"   事件: {match_details['event_title']}")
            print(f"   置信度: {match_details['match_score']:.2f}")
            print(f"   匹配关键词: {match_details['matched_keywords']}")
            print(f"   验证: {match_details['validation_reason']}")
        else:
            print("❌ 未匹配到任何事件")
            
            # 显示详细调试信息
            data = load_upcoming_events()
            pending = [e for e in data["events"] if e["status"] == "pending"]
            print(f"\n   当前有 {len(pending)} 个待处理事件:")
            for e in pending:
                core, auxiliary = classify_keywords(e.get("expected_keywords", []))
                print(f"   - {e['title']}")
                print(f"     核心: {core}")
                print(f"     辅助: {auxiliary}")
    
    elif args.command == "zeitgeist":
        if args.zgt_command == "add":
            keywords = [k.strip() for k in args.keywords.split(",")]
            entities = [e.strip() for e in args.entities.split(",") if e.strip()]
            zid = add_zeitgeist(
                topic=args.topic,
                description=args.description,
                category=args.category,
                keywords=keywords,
                heat_score=args.heat,
                trend=args.trend,
                related_entities=entities
            )
            print(f"✅ 已添加时代情绪: {zid}")

        elif args.zgt_command == "list":
            zeitgeist_list = load_zeitgeist()
            if args.status != "all":
                zeitgeist_list = [z for z in zeitgeist_list if z["status"] == args.status]
            if args.min_heat > 0:
                zeitgeist_list = [z for z in zeitgeist_list if z["heat_score"] >= args.min_heat]
            # 按热度排序
            zeitgeist_list.sort(key=lambda x: x["heat_score"], reverse=True)

            print(f"\n�� 时代情绪列表 ({len(zeitgeist_list)} 条)\n")
            for z in zeitgeist_list:
                trend_icon = {"上升": "📈", "稳定": "➡️", "下降": "📉", "周期性": "🔄"}.get(z.get("trend_name"), "•")
                status_icon = {"active": "🟢", "faded": "⚪", "realized": "✅"}.get(z["status"], "•")
                print(f"{status_icon} {z['topic']} {trend_icon}")
                print(f"   ID: {z['id']}")
                print(f"   描述: {z['description'][:60]}...")
                print(f"   类别: {z.get('category_name', '-')} | 热度: {z['heat_score']}/100 | 趋势: {z.get('trend_name', '-')}")
                print(f"   关键词: {', '.join(z.get('keywords', []))}")
                print(f"   提及次数: {z.get('mentions_count', 0)}")
                print()

        elif args.zgt_command == "heat":
            if update_zeitgeist_heat(args.id, args.score, args.note):
                print(f"✅ 已更新热度: {args.id} -> {args.score}")
            else:
                print(f"❌ 未找到情绪: {args.id}")

        elif args.zgt_command == "status":
            if update_zeitgeist_status(args.id, args.status, args.note):
                print(f"✅ 已更新状态: {args.id} -> {args.status}")
            else:
                print(f"❌ 未找到情绪: {args.id}")

        elif args.zgt_command == "summary":
            summary = get_zeitgeist_summary()
            print(f"\n🌊 时代情绪统计\n")
            print(f"  总计: {summary['total']}")
            print(f"  活跃中: {summary['active']} 🟢")
            print(f"  已消退: {summary['faded']} ⚪")
            print(f"  已实现: {summary['realized']} ✅")
            print(f"\n  按类别分布:")
            for cat, count in summary['by_category'].items():
                print(f"    {cat}: {count}")
            print(f"\n  按趋势分布:")
            for trend, count in summary['by_trend'].items():
                print(f"    {trend}: {count}")
            if summary['top_heat']:
                print(f"\n  🔥 热度最高:")
                for z in summary['top_heat'][:3]:
                    print(f"    - {z['topic']} ({z['heat_score']}/100)")
            if summary['rising']:
                print(f"\n  📈 上升趋势:")
                for z in summary['rising']:
                    print(f"    - {z['topic']}")

        else:
            # 默认显示时代情绪摘要
            summary = get_zeitgeist_summary()
            print(f"\n🌊 时代情绪摘要\n")
            print(f"  活跃中: {summary['active']} 条")
            if summary['top_heat']:
                print(f"\n  🔥 热门情绪:")
                for z in summary['top_heat'][:5]:
                    trend_icon = {"上升": "📈", "稳定": "➡️", "下降": "📉"}.get(z.get("trend_name"), "•")
                    print(f"    {trend_icon} {z['topic']} ({z['heat_score']}/100)")

    else:
        # 默认显示预告事件摘要 + 时代情绪摘要
        summary = get_pending_events_summary()
        print(f"\n📊 预告事件统计\n")
        print(f"  总计: {summary['total']}")
        print(f"  待处理: {summary['pending']}")
        print(f"  已找到: {summary['found']}")
        print(f"  已过期: {summary['expired']}")

        if summary['pending_list']:
            print(f"\n  待处理事件:\n")
            for e in summary['pending_list']:
                print(f"    - {e['title']} ({e['source_hint']})")
                print(f"      核心词: {', '.join(e['core_keywords'])}")
                print(f"      辅助词: {', '.join(e['auxiliary_keywords'])}")

        # 显示时代情绪
        z_summary = get_zeitgeist_summary()
        if z_summary['active'] > 0:
            print(f"\n🌊 时代情绪 ({z_summary['active']} 条活跃)\n")
            for z in z_summary['top_heat'][:3]:
                trend_icon = {"上升": "📈", "稳定": "➡️", "下降": "📉"}.get(z.get("trend_name"), "•")
                print(f"  {trend_icon} {z['topic']} ({z['heat_score']}/100) - {z.get('category_name', '')}")
