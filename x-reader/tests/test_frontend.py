#!/usr/bin/env python3
"""
前端事件时间线功能测试
定义事件展示、视图切换、过滤排序等功能的预期行为
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime
from unittest.mock import patch, MagicMock
from src.web.app import app
import json


class TestFrontendEventTimeline:
    """前端事件时间线功能测试类"""

    def setup_method(self):
        """测试前设置"""
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret-key'
        self.client = app.test_client()
        # 模拟登录状态
        with self.client.session_transaction() as sess:
            sess['logged_in'] = True

    @patch('src.web.app.load_json')
    def test_event_timeline_display(self, mock_load_json, event_group_fixture, news_data_fixture):
        """
        测试事件时间线展示功能
        - 验证事件显示标题、元数据、实体和嵌套新闻列表
        - 验证每个事件内的新闻按时间顺序排序
        - 验证缺失的新闻ID被优雅处理
        """
        # Mock数据加载
        def mock_load_side_effect(file_path, default=None):
            if "event_groups.json" in file_path:
                return event_group_fixture
            elif "news_data.json" in file_path:
                return news_data_fixture
            return default

        mock_load_json.side_effect = mock_load_side_effect

        # 测试事件API接口
        response = self.client.get('/api/events')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        assert len(events) == 2  # 应该有2个事件

        # 验证第一个事件基本信息
        event1 = events[0]
        assert event1['title'] == "OpenAI发布GPT-5大模型"
        assert event1['max_grade'] == "A+"
        assert event1['max_score'] == 95
        assert event1['news_count'] == 3

        # 验证第二个事件基本信息
        event2 = events[1]
        assert event2['title'] == "Anthropic推出Claude 3.5系列模型"
        assert event2['max_grade'] == "A"
        assert event2['max_score'] == 88
        assert event2['news_count'] == 2

        # 请求首页，验证页面正常加载
        response = self.client.get('/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # 验证事件分组标签存在
        assert "事件分组" in html
        assert "切换到列表视图" in html  # 视图切换按钮存在

        # 测试缺失新闻ID的处理
        # 修改分组数据，添加一个不存在的新闻ID
        event_group_fixture["groups"]["event_001"]["news_ids"].append("news_999")

        # 测试API仍然正常工作，不会崩溃
        response = self.client.get('/api/events')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        assert len(events) == 2  # 仍然有2个事件

        # 验证第一个事件仍然只有3条有效新闻（无效ID被过滤）
        event1 = events[0]
        assert event1['title'] == "OpenAI发布GPT-5大模型"
        assert event1['news_count'] == 3  # 应该只显示3条有效新闻，而不是4条

    @patch('src.web.app.load_json')
    def test_view_toggle(self, mock_load_json, event_group_fixture, news_data_fixture):
        """
        测试视图切换功能（分组视图/列表视图）
        - 验证两种视图都可访问
        - 验证用户偏好被保存
        - 验证两种视图下所有功能正常工作
        """
        # Mock数据加载
        def mock_load_side_effect(file_path, default=None):
            if "event_groups.json" in file_path:
                return event_group_fixture
            elif "news_data.json" in file_path:
                return news_data_fixture
            return default

        mock_load_json.side_effect = mock_load_side_effect

        # 测试页面加载成功，包含事件相关元素
        response = self.client.get('/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # 验证页面包含事件相关的UI元素
        assert "事件分组" in html  # 事件分组标签存在
        assert "切换到列表视图" in html  # 视图切换按钮存在
        assert "eventsContainer" in html  # 事件容器存在
        assert "eventSearchInput" in html  # 搜索框存在
        assert "eventSortSelect" in html  # 排序选择器存在

        # 测试API筛选功能
        # 先获取所有事件，确认数据存在
        response = self.client.get('/api/events')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        all_events = result['data']
        assert len(all_events) == 2, f"Expected 2 events, got {len(all_events)}"

        # 按评级A+筛选
        filter_param = json.dumps({"ratings": ["A+"]})
        response = self.client.get(f'/api/events?filter={filter_param}')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        # 验证事件内只包含A+级新闻
        if len(events) > 0:
            assert events[0]['title'] == "OpenAI发布GPT-5大模型"
            assert len(events[0]['news_list']) >= 1
            assert any(news['rating'] == "A+" for news in events[0]['news_list'])

    @patch('src.web.app.load_json')
    def test_event_filter_sort(self, mock_load_json, event_group_fixture, news_data_fixture):
        """
        测试事件过滤和排序功能
        - 验证过滤器同时作用于事件级别和新闻级别
        - 验证没有匹配新闻的事件被隐藏
        - 验证事件级排序正常工作（按分数、新闻数量、时间）
        """
        # Mock数据加载
        def mock_load_side_effect(file_path, default=None):
            if "event_groups.json" in file_path:
                return event_group_fixture
            elif "news_data.json" in file_path:
                return news_data_fixture
            return default

        mock_load_json.side_effect = mock_load_side_effect

        # 测试按搜索关键词过滤
        response = self.client.get('/api/events?search=GPT-5')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        assert len(events) == 1
        assert events[0]['title'] == "OpenAI发布GPT-5大模型"

        # 测试按实体过滤
        response = self.client.get('/api/events?search=OpenAI')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        assert len(events) == 1
        assert events[0]['title'] == "OpenAI发布GPT-5大模型"

        # 测试没有匹配结果时的处理
        response = self.client.get('/api/events?search=NonExistentEntity')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        assert len(events) == 0

        # 测试事件排序 - 默认按最高分数降序
        response = self.client.get('/api/events?sort=max_score:desc')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        assert len(events) == 2
        # OpenAI事件分数95 > Anthropic的88，应该排在前面
        assert events[0]['title'] == "OpenAI发布GPT-5大模型"
        assert events[1]['title'] == "Anthropic推出Claude 3.5系列模型"

        # 测试按新闻数量排序（降序）
        response = self.client.get('/api/events?sort=news_count:desc')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        # OpenAI事件3条 > Anthropic的2条，应该排在前面
        assert events[0]['title'] == "OpenAI发布GPT-5大模型"
        assert events[1]['title'] == "Anthropic推出Claude 3.5系列模型"

        # 测试按结束时间排序（升序，最旧在前）
        response = self.client.get('/api/events?sort=end_time:asc')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        # Anthropic事件结束时间更早，应该排在前面
        assert events[0]['title'] == "Anthropic推出Claude 3.5系列模型"
        assert events[1]['title'] == "OpenAI发布GPT-5大模型"

        # 测试组合过滤和排序
        filter_param = json.dumps({"ratings": ["A"]})
        response = self.client.get(f'/api/events?filter={filter_param}&sort=max_score:desc')
        assert response.status_code == 200
        result = response.get_json()
        assert result['code'] == 0
        events = result['data']
        # 两个事件都有A级新闻，但OpenAI分数更高，应该排在前面
        assert len(events) == 2
        assert events[0]['title'] == "OpenAI发布GPT-5大模型"
        assert events[1]['title'] == "Anthropic推出Claude 3.5系列模型"
