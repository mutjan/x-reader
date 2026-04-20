#!/usr/bin/env python3
"""测试/api/events端点功能"""
import json
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.web.app import app
from src.config.settings import EVENT_GROUPS_FILE, DATA_FILE

def test_api_events():
    """测试事件API功能"""
    # 创建测试客户端
    client = app.test_client()

    # 模拟登录
    with client.session_transaction() as sess:
        sess['logged_in'] = True

    # 测试基本API调用
    response = client.get('/api/events')
    assert response.status_code == 200

    data = json.loads(response.data)
    assert data['code'] == 0
    assert 'data' in data
    assert 'total' in data
    assert 'page' in data
    assert 'page_size' in data

    print(f"✓ API调用成功，返回状态码: {response.status_code}")
    print(f"✓ 返回结构正确，共 {data['total']} 个事件")

    # 检查事件结构
    if data['data']:
        event = data['data'][0]
        required_fields = ['event_id', 'title', 'max_grade', 'max_score', 'start_time', 'end_time', 'news_count', 'entities', 'news_list']
        for field in required_fields:
            assert field in event, f"缺少字段: {field}"
        print("✓ 事件结构完整，包含所有必填字段")

        # 检查新闻嵌套结构
        assert event['news_count'] == len(event['news_list'])
        print(f"✓ 事件包含 {event['news_count']} 条嵌套新闻")

        # 检查新闻结构
        if event['news_list']:
            news = event['news_list'][0]
            assert 'id' in news
            assert 'title' in news
            assert 'score' in news
            print("✓ 嵌套新闻结构完整")

    # 测试分页
    response = client.get('/api/events?page=1&page_size=1')
    data = json.loads(response.data)
    assert len(data['data']) == 1
    print("✓ 分页功能正常")

    # 测试搜索（使用真实数据中存在的关键词）
    response = client.get('/api/events?search=AI')
    data = json.loads(response.data)
    print(f"搜索 'AI' 返回 {data['total']} 个结果")
    assert data['total'] >= 1, f"搜索'AI'应该返回至少1个结果，实际返回{data['total']}个"
    print("✓ 搜索功能正常")

    # 测试排序（只有当事件数量>=2时才测试）
    if len(data['data']) >= 2:
        response = client.get('/api/events?sort=news_count:desc')
        data = json.loads(response.data)
        assert data['data'][0]['news_count'] >= data['data'][1]['news_count']
        print("✓ 排序功能正常")
    else:
        print("⚠ 事件数量不足，跳过排序测试")

    # 测试过滤
    filter_param = json.dumps({"score_min": 80})
    response = client.get(f'/api/events?filter={filter_param}')
    data = json.loads(response.data)
    # 检查事件中的新闻是否都符合过滤条件
    if data['data']:
        for event in data['data']:
            for news in event['news_list']:
                assert news.get('score', 0) >= 80
        print("✓ 过滤功能正常")
    else:
        print("⚠ 没有符合过滤条件的事件，跳过滤测试")

    print("\n✅ 所有测试通过!")

    # 打印示例响应
    print("\n示例响应预览:")
    response = client.get('/api/events?page_size=1')
    data = json.loads(response.data)
    print(json.dumps(data['data'][0], ensure_ascii=False, indent=2))

if __name__ == '__main__':
    test_api_events()
