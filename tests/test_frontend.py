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

        # 请求首页
        response = self.client.get('/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')

        # 验证事件基本信息显示
        assert "OpenAI发布GPT-5大模型" in html
        assert "A+" in html  # 最高评级
        assert "95" in html  # 最高分数
        assert "3条相关新闻" in html  # 新闻数量

        # 验证事件实体显示
        assert "OpenAI" in html
        assert "GPT" in html
        assert "大模型" in html
        assert "AI" in html

        # 验证时间范围显示
        assert "2026-04-01" in html
        assert "2026-04-02" in html

        # 验证嵌套新闻列表显示（按时间顺序排序）
        # 最早的新闻应该显示在最上面
        assert "OpenAI发布GPT-5，支持100万上下文窗口" in html
        assert "GPT-5基准测试显示全任务SOTA性能" in html
        assert "OpenAI公布GPT-5 API定价和可用性" in html

        # 验证第二个事件显示
        assert "Anthropic推出Claude 3.5系列模型" in html
        assert "A" in html
        assert "88" in html
        assert "2条相关新闻" in html

        # 测试缺失新闻ID的处理
        # 修改分组数据，添加一个不存在的新闻ID
        event_group_fixture["groups"]["event_001"]["news_ids"].append("news_999")
        response = self.client.get('/')
        assert response.status_code == 200
        # 页面应该正常加载，不会报错
        html = response.data.decode('utf-8')
        assert "OpenAI发布GPT-5大模型" in html
        # 应该只显示3条有效新闻，而不是4条
        assert "3条相关新闻" in html

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

        # 测试默认视图（分组视图）
        response = self.client.get('/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "事件分组视图" in html or "分组视图" in html
        assert "OpenAI发布GPT-5大模型" in html  # 事件标题显示

        # 测试切换到列表视图
        response = self.client.get('/?view=list')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "列表视图" in html
        # 列表视图应该直接显示所有新闻，不分组
        assert "OpenAI发布GPT-5，支持100万上下文窗口" in html
        assert "GPT-5基准测试显示全任务SOTA性能" in html
        assert "OpenAI公布GPT-5 API定价和可用性" in html
        assert "Anthropic发布Claude 3.5，推理能力显著提升" in html
        assert "Claude 3.5编码基准测试超越GPT-4" in html
        assert "特斯拉发布Optimus Gen 2人形机器人" in html

        # 测试切换回分组视图
        response = self.client.get('/?view=grouped')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "事件分组视图" in html or "分组视图" in html
        assert "OpenAI发布GPT-5大模型" in html

        # 测试用户偏好保存（通过Cookie）
        response = self.client.get('/?view=list')
        assert response.status_code == 200
        assert 'view=list' in response.headers.get('Set-Cookie', '')

        # 后续请求不带参数时应该使用Cookie中的偏好
        response = self.client.get('/', headers={'Cookie': 'view=list'})
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "列表视图" in html

        # 测试两种视图下筛选功能都正常
        # 列表视图筛选
        response = self.client.get('/?view=list&grade=A%2B')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "GPT-5基准测试显示全任务SOTA性能" in html
        assert "OpenAI发布GPT-5，支持100万上下文窗口" not in html  # A级不显示

        # 分组视图筛选
        response = self.client.get('/?view=grouped&grade=A%2B')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "OpenAI发布GPT-5大模型" in html  # 事件包含A+级新闻，应该显示
        assert "Anthropic推出Claude 3.5系列模型" not in html  # 事件最高是A级，不显示

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

        # 测试按评级过滤
        response = self.client.get('/?grade=A%2B')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "OpenAI发布GPT-5大模型" in html  # 有A+级新闻
        assert "Anthropic推出Claude 3.5系列模型" not in html  # 最高是A级
        # 验证事件内只显示匹配的新闻
        assert "GPT-5基准测试显示全任务SOTA性能" in html  # A+级
        assert "OpenAI发布GPT-5，支持100万上下文窗口" not in html  # A级被过滤

        # 测试按实体过滤
        response = self.client.get('/?entity=OpenAI')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "OpenAI发布GPT-5大模型" in html
        assert "Anthropic推出Claude 3.5系列模型" not in html

        # 测试按关键词过滤
        response = self.client.get('/?q=GPT-5')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "OpenAI发布GPT-5大模型" in html
        assert "Anthropic推出Claude 3.5系列模型" not in html

        # 测试没有匹配结果时的处理
        response = self.client.get('/?entity=NonExistentEntity')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        assert "没有找到匹配的新闻" in html or "暂无数据" in html

        # 测试事件排序 - 默认按最新时间排序
        response = self.client.get('/')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        # OpenAI事件更新时间更近，应该排在前面
        assert html.index("OpenAI发布GPT-5大模型") < html.index("Anthropic推出Claude 3.5系列模型")

        # 测试按分数排序（降序）
        response = self.client.get('/?sort=score')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        # OpenAI事件分数95 > Anthropic的88，应该排在前面
        assert html.index("OpenAI发布GPT-5大模型") < html.index("Anthropic推出Claude 3.5系列模型")

        # 测试按新闻数量排序（降序）
        response = self.client.get('/?sort=count')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        # OpenAI事件3条 > Anthropic的2条，应该排在前面
        assert html.index("OpenAI发布GPT-5大模型") < html.index("Anthropic推出Claude 3.5系列模型")

        # 测试按时间排序（升序，最旧在前）
        response = self.client.get('/?sort=time_asc')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        # 两个事件开始时间相同，按结束时间排序，Anthropic更早结束，应该排在前面
        assert html.index("Anthropic推出Claude 3.5系列模型") < html.index("OpenAI发布GPT-5大模型")

        # 测试组合过滤和排序
        response = self.client.get('/?grade=A&sort=score')
        assert response.status_code == 200
        html = response.data.decode('utf-8')
        # 两个事件都有A级新闻，但OpenAI分数更高，应该排在前面
        assert html.index("OpenAI发布GPT-5大模型") < html.index("Anthropic推出Claude 3.5系列模型")
