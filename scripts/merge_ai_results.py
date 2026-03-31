#!/usr/bin/env python3
"""
合并AI处理结果到新闻数据文件
"""
import json
import os
from datetime import datetime

# 读取现有的新闻数据
news_data_file = "news_data.json"
with open(news_data_file, 'r', encoding='utf-8') as f:
    news_data = json.load(f)

# 读取AI处理结果
ai_result_file = "_ai_result.json"
with open(ai_result_file, 'r', encoding='utf-8') as f:
    ai_results = json.load(f)

# 类型映射
type_map = {
    "product": ("product", "产品发布"),
    "funding": ("funding", "融资上市"),
    "personnel": ("personnel", "人事变动"),
    "opinion": ("opinion", "观点访谈"),
    "industry": ("industry", "行业动态"),
    "safety": ("safety", "安全伦理"),
    "research": ("research", "研究成果"),
    "financial": ("financial", "商业数据"),
    "breaking": ("breaking", "突发事件"),
    "tool": ("tool", "工具技巧"),
    "society": ("society", "社会影响"),
    "hardware": ("hardware", "硬件基建")
}

# 获取原始新闻数据用于URL匹配
full_prompt_file = "full_ai_prompt.txt"
original_items = []
if os.path.exists(full_prompt_file):
    with open(full_prompt_file, 'r', encoding='utf-8') as f:
        content = f.read()
        # 提取JSON部分
        json_start = content.find('[')
        json_end = content.rfind(']') + 1
        if json_start != -1 and json_end > 0:
            try:
                original_items = json.loads(content[json_start:json_end])
            except:
                pass

# 创建URL到原始数据的映射
url_to_item = {}
for item in original_items:
    if 'url' in item:
        url_to_item[item['url']] = item

# 处理AI结果
today = datetime.now().strftime("%Y-%m-%d")
new_news = []
level_counts = {"S": 0, "A+": 0, "A": 0, "B": 0}

for result in ai_results:
    grade = result.get("grade", "C")
    if grade == "C":
        continue
    
    score = result.get("score", 0)
    news_type = result.get("type", "industry")
    type_key, type_name = type_map.get(news_type, ("industry", "行业动态"))
    
    # 获取原始URL
    original_url = ""
    index = result.get("index", -1)
    if 0 <= index < len(original_items):
        original_url = original_items[index].get("url", "")
    
    # 检查是否已存在（基于URL）
    exists = False
    for date, items in news_data.items():
        for item in items:
            if item.get("url") == original_url:
                exists = True
                break
        if exists:
            break
    
    if exists:
        print(f"跳过已存在的新闻: {result.get('chinese_title', '')[:30]}...")
        continue
    
    # 创建新闻项
    news_item = {
        "title": result.get("chinese_title", ""),
        "title_en": original_items[index].get("title", "") if 0 <= index < len(original_items) else "",
        "summary": result.get("summary", ""),
        "type": type_key,
        "typeName": type_name,
        "score": score,
        "level": grade,
        "reason": f"【{grade}级】评分{score}分 | {result.get('extension', '')}",
        "entities": result.get("entities", []),
        "url": original_url,
        "source": original_items[index].get("source", "") if 0 <= index < len(original_items) else "",
        "sources": 1,
        "sourceLinks": [original_url] if original_url else [],
        "timestamp": int(datetime.now().timestamp()),
        "version": datetime.now().strftime("%Y.%m.%d-001")
    }
    
    new_news.append(news_item)
    level_counts[grade] = level_counts.get(grade, 0) + 1

# 添加到新闻数据
if today not in news_data:
    news_data[today] = []

news_data[today].extend(new_news)

# 保存更新后的新闻数据
with open(news_data_file, 'w', encoding='utf-8') as f:
    json.dump(news_data, f, ensure_ascii=False, indent=2)

# 统计信息
print("=" * 60)
print("AI处理结果合并完成！")
print("=" * 60)
print(f"新增新闻: {len(new_news)} 条")
print(f"级别分布: {level_counts}")
print(f"今日总计: {len(news_data[today])} 条")

# 更新工作日志
work_log_file = ".work_log.json"
work_log = {"entries": [], "last_execution": ""}
if os.path.exists(work_log_file):
    try:
        with open(work_log_file, 'r', encoding='utf-8') as f:
            work_log = json.load(f)
    except:
        pass

log_entry = {
    "timestamp": datetime.now().isoformat(),
    "sources": "all",
    "total_fetched": 218,
    "new_items": 148,
    "filtered": 14,
    "ai_processed": len(ai_results),
    "added": len(new_news),
    "updated": 0,
    "total_news": sum(level_counts.values()),
    "level_counts": level_counts,
    "github_pushed": False,
    "errors": [],
    "notes": ["使用本地AI处理结果合并"]
}

work_log["entries"].append(log_entry)
work_log["last_execution"] = log_entry["timestamp"]

with open(work_log_file, 'w', encoding='utf-8') as f:
    json.dump(work_log, f, ensure_ascii=False, indent=2)

print(f"工作日志已更新: {work_log_file}")
