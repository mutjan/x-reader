import json
from datetime import datetime

with open('news_data.json', 'r') as f:
    data = json.load(f)

news_by_date = data.get('news', {})
total = 0
grades = {}
recent_news = []

for date, news_list in news_by_date.items():
    total += len(news_list)
    for item in news_list:
        grade = item.get('rating', 'unknown')
        grades[grade] = grades.get(grade, 0) + 1
        # 收集所有新闻用于排序
        recent_news.append({
            'date': date,
            'published_at': item.get('published_at', ''),
            'title': item.get('title', '无标题'),
            'grade': grade
        })

print(f"总新闻数: {total}")
print(f"覆盖日期: {len(news_by_date)} 天")

print("\n级别分布:")
for grade, count in sorted(grades.items()):
    print(f"  {grade}: {count} 条")

# 按时间排序取最近10条
recent_news.sort(key=lambda x: x['published_at'], reverse=True)
print("\n最近10条新闻:")
for item in recent_news[:10]:
    print(f"  {item['date']} {item['grade']:2} - {item['title'][:40]}...")

# 查看本次新增的新闻（4月1日）
print("\n本次新增新闻(2026-04-01):")
if '2026-04-01' in news_by_date:
    today_news = news_by_date['2026-04-01']
    print(f"  今日新增: {len(today_news)} 条")
    grades_today = {}
    for item in today_news:
        grade = item.get('rating', 'unknown')
        grades_today[grade] = grades_today.get(grade, 0) + 1
    print("  今日级别分布:")
    for grade, count in sorted(grades_today.items()):
        print(f"    {grade}: {count} 条")
else:
    print("  今日暂无新增新闻")
