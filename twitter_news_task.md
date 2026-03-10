# Twitter RSS 新闻选题定时任务

## 任务概述

每小时从 Twitter List RSS 源获取最新内容，进行选题筛选并推送到 GitHub Pages。

## RSS 源

- **地址**: `http://localhost:1200/twitter/list/2026563584311108010`
- **获取范围**: 最近 1 小时内发布的内容

## 工作流程

### 1. 获取 RSS 内容

```bash
curl -s "http://localhost:1200/twitter/list/2026563584311108010"
```

解析 RSS XML，提取以下字段：
- `title`: 推文标题/内容
- `content`: 完整内容
- `url`: 原文链接
- `source`: 来源账号
- `published`: 发布时间

### 2. 筛选最近 1 小时内容

根据 `published` 时间戳，筛选出最近 1 小时内发布的内容。

### 3. 选题筛选（本地模型处理）

使用本地模型（Claude）对新闻进行批量处理：

**筛选标准**（S级/A级/B级）：
- S级（90-100分）：AI大模型重大发布、马斯克/SpaceX重大动态、Nature/Science顶刊
- A级（75-89分）：科技巨头动态、国产大模型、开源爆款、学术突破、人物故事
- B级（60-74分）：产品评测、技术解析、航天/芯片
- 过滤掉C级（<60分）：一般商业新闻、消费电子

**生成内容**：
- 量子位风格中文标题（20-40字，情绪饱满）
- 一句话摘要（50-100字）
- 类型标注：hot(热点)/ai(AI相关)/tech(科技)/business(商业)

### 4. 去重与合并

**与当日已有选题去重**：
- 读取 `news_data.json` 中当日的已有选题
- 使用标题相似度（Jaccard）判断是否为同一事件
- 相似度 > 0.5 认为是同一事件

**重复处理策略**：
- 如果新选题与当日已有选题重复：
  - 保留原有标题、摘要、评分
  - 只增加新的消息来源链接到 `sourceLinks`
  - 更新 `sources` 计数
- 如果是新选题：
  - 正常添加到当日列表

### 5. 推送到 GitHub

- 更新 `news_data.json`
- 保留最近 30 天数据
- 自动 commit 并 push 到 GitHub Pages

## 输出格式

```json
{
  "title": "效果炸裂！OpenAI发布新一代模型",
  "title_en": "OpenAI releases new model",
  "summary": "OpenAI最新发布的大模型在多项基准测试中创下新高...",
  "type": "ai",
  "typeName": "AI",
  "score": 85,
  "level": "A",
  "reason": "【A级优先】评分85分 | OpenAI重大发布",
  "url": "https://twitter.com/...",
  "source": "Twitter/@username",
  "sources": 2,
  "sourceLinks": [
    {"name": "Twitter/@user1", "url": "https://twitter.com/..."},
    {"name": "Twitter/@user2", "url": "https://twitter.com/..."}
  ],
  "timestamp": 1773034482,
  "version": "2026.03.09-001"
}
```

## 文件说明

- `update_news.py`: 主脚本（Inoreader 版本）
- `update_twitter_news.py`: Twitter RSS 版本脚本（需创建）
- `news_data.json`: 新闻数据存储
- `twitter_news_task.md`: 本文档

## 注意事项

1. **不要创建规则引擎**：所有选题筛选必须由本地模型完成
2. **RSS 服务假设**：`localhost:1200` 是 rsshub 服务，需确保其运行
3. **代理设置**：如需代理，使用 `socks5h://127.0.0.1:7890`
4. **GitHub Token**: 使用环境变量或配置文件中的 token
