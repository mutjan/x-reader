# Twitter RSS 新闻选题工具

从 Twitter RSS 源自动获取科技新闻，通过 AI 筛选和加工，生成适合科技媒体发布的选题。

## 功能特性

- **RSS 自动获取**: 从 Twitter List RSS 源获取最新内容
- **关键词预筛选**: 基于关键词匹配确保重要新闻不被遗漏
- **预告事件追踪**: 维护已预告事件列表，主动搜索匹配新消息
- **AI 智能处理**: 支持两种模式
  - **自动 API 模式**: 配置 API Key 后全自动处理
  - **本地模型模式**: 生成提示词供 Claude Desktop 等本地模型处理
- **智能去重**: 基于标题相似度和核心实体识别合并重复新闻
- **分级管理**: S/A/B 三级选题分类
- **GitHub 同步**: 自动推送到 GitHub Pages

## 快速开始

### 1. 安装依赖

```bash
# 确保使用 Python 3
python3 --version

# 安装依赖（如果需要）
pip3 install requests
```

### 2. 配置 API Key（推荐）

```bash
# 运行配置向导
python3 setup_config.py
```

或者手动设置环境变量：

```bash
export MOONSHOT_API_KEY="sk-..."
```

### 3. 添加预告事件（可选）

追踪即将发生的重要事件：

```bash
# 添加预告事件
python3 upcoming_events.py add \
  --title "No Priors 预告：Karpathy 将做客下期节目" \
  --keywords "No Priors,Karpathy,podcast" \
  --source "No Priors 播客" \
  --priority A+

# 查看待处理事件
python3 upcoming_events.py list
```

### 4. 运行脚本

```bash
# 全自动模式（已配置 API Key）
python3 update_news.py

# 半自动模式（无 API Key）
python3 update_news.py
# 按提示将 twitter_ai_prompt.txt 发送给 Claude Desktop 处理
# 将结果保存为 twitter_ai_result.json
# 再次运行脚本
```

## 工作流程

```
┌─────────────────┐
│  获取 RSS 内容   │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  筛选最近12小时  │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  关键词预筛选    │ ← 确保重要新闻不被遗漏
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   AI 处理       │ ← API 自动调用或本地模型
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  去重与合并     │
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  推送到 GitHub  │
└─────────────────┘
```

## 关键词预筛选

脚本内置了丰富的关键词库，涵盖：

- **AI 大模型**: GPT-5、Claude、Gemini、DeepSeek、Agent、AGI 等
- **科技巨头**: OpenAI、Google、Microsoft、Meta、NVIDIA、字节、腾讯、阿里等
- **芯片/硬件**: H100、B200、CUDA、AI Chip 等
- **人物动态**: Musk、Altman、Hassabis、Karpathy 等
- **科研突破**: Nature、Science、arXiv、里程碑等
- **商业动态**: IPO、融资、估值、收购等
- **具身智能**: Robotics、Robot、Embodied AI 等

## 选题分级标准

### S级（90-100分）
- AI 大模型重大发布（GPT-5、Claude 4、Gemini 2 等）
- 马斯克/SpaceX/Neuralink 重大动态
- Nature/Science/Cell 顶刊发表
- 科技巨头重大战略调整或人事变动
- AGI 相关重大进展或权威预测
- 顶级 AI 研究者的重大开源项目

### A级（75-89分）
- 科技巨头产品更新
- 国产大模型重要进展
- 开源项目爆款/Star 数激增
- 学术突破（arXiv 重要论文）
- 知名人物专访或重要观点
- 资本市场重大动态
- 重要技术突破

### B级（60-74分）
- 产品评测、体验报告
- 技术解析、教程
- 航天/芯片领域常规进展
- 行业数据报告

## 文件说明

| 文件 | 说明 |
|------|------|
| `update_twitter_news.py` | 主脚本 |
| `setup_config.py` | 配置向导 |
| `twitter_ai_prompt.txt` | AI 处理提示词（自动生成） |
| `twitter_ai_result.json` | AI 处理结果（自动生成） |
| `news_data.json` | 新闻数据存储 |
| `.version_counter` | 版本计数器 |

## 配置选项

### RSS 源配置

编辑脚本中的 `RSS_URL`：

```python
RSS_URL = "http://localhost:1200/twitter/list/2026563584311108010?filter_time=86400"
```

需要本地运行 [RSSHub](https://docs.rsshub.app/) 服务。

### GitHub 配置

```python
GITHUB_REPO = "x-reader"
GITHUB_BRANCH = "main"
```

### 关键词配置

编辑脚本中的 `PRIORITY_KEYWORDS` 字典，添加或调整关键词。

## 常见问题

### Q: 如何切换到本地模型模式？

A: 不配置 API Key 即可。脚本会自动生成提示词，需要手动发送给 Claude Desktop 处理。

### Q: API 调用失败怎么办？

A: 脚本会自动回退到本地模型模式，按提示操作即可。

### Q: 如何调整时间范围？

A: 修改脚本中的 `hours` 参数：

```python
recent_items = filter_recent_items(items, hours=24)  # 改为24小时
```

### Q: 如何修改分级阈值？

A: 编辑 AI 提示词中的分级标准，或修改 `ai_process_items` 函数中的评分逻辑。

## 预告事件追踪

维护已预告的重要事件列表，主动搜索是否有新消息发布。

### 使用场景

- **播客预告**：No Priors 预告下期嘉宾是 Karpathy
- **产品预告**：OpenAI 预告 GPT-5 即将发布
- **会议预告**：某峰会预告重磅演讲嘉宾

### 工作流程

```
┌─────────────────────────────────┐
│  添加预告事件到 upcoming_events  │
└───────────────┬─────────────────┘
                │
                ▼
┌─────────────────────────────────┐
│  每次新闻更新时自动检查匹配      │
└───────────────┬─────────────────┘
                │
        ┌───────┴───────┐
        ▼               ▼
┌──────────────┐ ┌──────────────┐
│   匹配成功    │ │   未匹配      │
└──────┬───────┘ └──────────────┘
       │
       ▼
┌─────────────────────────────────┐
│  从预告列表移除                  │
│  加入正式选题列表（标记预告落地） │
└─────────────────────────────────┘
```

### CLI 命令

```bash
# 添加预告事件
python3 upcoming_events.py add \
  --title "事件标题" \
  --description "事件描述" \
  --keywords "关键词1,关键词2,关键词3" \
  --source "来源提示" \
  --priority A+

# 列出所有待处理事件
python3 upcoming_events.py list

# 列出所有事件（包括已找到/已过期）
python3 upcoming_events.py list --status all

# 移除指定事件
python3 upcoming_events.py remove evt_20260318_xxxxxx

# 清理30天前的过期事件
python3 upcoming_events.py cleanup
```

### 匹配逻辑

- 支持多关键词匹配（2+ 个关键词命中即认为匹配）
- 检查标题、内容和 URL
- 匹配成功后自动转换并加入新闻列表
- 新闻标题会标记【预告落地】前缀

---

## 更新日志

### v3.0 (2026-03-18)
- ✨ 新增预告事件追踪功能
- ✨ 支持主动搜索预告事件的新消息
- 🔧 整合 Twitter 和 Inoreader 数据源

### v2.0 (2026-03-11)
- ✨ 新增自动 API 调用模式
- ✨ 新增配置向导脚本
- ✨ 扩展关键词库（新增具身智能、RLHF、MoE 等）
- 🔧 修复 Python 版本检测
- 🔧 优化错误处理和日志

### v1.0
- 初始版本
- RSS 获取与解析
- 关键词预筛选
- AI 处理与去重
- GitHub 推送

## License

MIT
