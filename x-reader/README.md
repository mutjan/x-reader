# 科技新闻选题聚合系统 x-reader

🌐 **在线部署页面**: [https://mutjan.github.io/x-reader](https://mutjan.github.io/x-reader)

多源科技新闻聚合与AI选题系统，从Twitter、Inoreader等数据源自动获取内容，通过智能筛选和加工，生成适合科技媒体发布的高质量选题。

## 功能特性

- **多源数据聚合**: 支持 Twitter、Inoreader 等多数据源，可扩展更多来源
- **模块化架构**: 采�工厂模式设计，数据源、处理器、发布器完全解耦
- **关键词预筛选**: 基于关键词匹配确保重要新闻不被遗漏
- **预告事件追踪**: 维护已预告事件列表，主动搜索匹配新消息
- **AI 智能处理**: 支持两种模式
  - **手动模式**: 生成提示词供 Claude Desktop 等本地模型处理（默认）
  - **自动 API 模式**: 配置 API Key 后全自动处理
- **智能去重**: 基于标题相似度和核心实体识别合并重复新闻
- **分级管理**: S/A+/A/B 四级选题分类
- **分类系统**: 12种新闻类型（AI、热点、商业、科研、产品、开源、人物、资本、政策、硬件、航天、其他）
- **GitHub 同步**: 自动推送到 GitHub Pages
- **断点续处理**: 支持中断后恢复处理流程，避免重复工作
- **前端交互**: 支持按评分、评级、类型、时间排序，点击实体标签快速筛选

## 快速开始

### 1. 安装依赖

```bash
# 确保使用 Python 3
python3 --version

# 安装依赖（如果需要）
pip3 install requests
```

### 2. 配置 API Key（可选，自动模式需要）

手动设置环境变量：

```bash
export MOONSHOT_API_KEY="sk-..."
```

### 3. 运行主程序

```bash
# 默认模式：获取所有数据源，手动处理
python3 main.py

# 指定数据源
python3 main.py --source twitter  # 仅获取Twitter
python3 main.py --source inoreader  # 仅获取Inoreader
python3 main.py --source all  # 获取所有数据源（默认）

# 运行后按照提示操作：
# 1. 脚本会自动获取并筛选新闻
# 2. 生成AI处理提示词
# 3. 将提示词发送给Claude处理，将结果保存为_ai_result.json
# 4. 再次运行脚本自动完成后续流程
```

### 4. 断点续处理（如果处理中断）

```bash
# 从中断处继续处理，无需重新获取数据
python3 continue_process.py
```

### 5. 添加预告事件（可选）

追踪即将发生的重要事件，使用管理后台：

```bash
# 查看管理后台帮助
python3 admin.py --help
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

## 项目结构

```
x-reader/
├── main.py                 # 主程序入口
├── admin.py                # 管理后台入口
├── continue_process.py     # 断点续处理工具
├── upcoming_events.py      # 预告事件和时代情绪管理
├── requirements.txt        # 依赖配置
├── index.html              # GitHub Pages前端
├── news_data.json          # 主数据文件
├── upcoming_events.json    # 预告事件数据
├── scripts/                # 工具脚本目录
│   ├── auth_inoreader.py   # Inoreader授权工具
│   ├── convert_data_format.py  # 数据格式转换工具
│   ├── import_results.py   # AI结果导入工具
│   ├── manual_process.py   # 手动处理脚本
│   └── test_classification.py  # 分类验证工具
├── src/                    # 模块化业务代码
│   ├── config/             # 配置文件
│   ├── fetchers/           # 数据源层（Twitter、Inoreader等）
│   ├── processors/         # 处理层（筛选、去重、AI处理等）
│   ├── publishers/         # 发布层（GitHub Pages等）
│   ├── models/             # 数据模型
│   └── utils/              # 工具函数
└── .processed_ids.json     # 处理记录缓存
```

### 核心文件说明

#### 根目录入口脚本
| 文件 | 说明 |
|------|------|
| `main.py` | 新的模块化主程序入口，替代所有旧版脚本 |
| `admin.py` | 系统管理后台，提供数据统计、事件管理等功能 |
| `continue_process.py` | 断点续处理工具，中断后恢复处理流程 |
| `upcoming_events.py` | 预告事件和时代情绪管理工具 |

#### 工具脚本（scripts目录）
| 文件 | 说明 |
|------|------|
| `scripts/auth_inoreader.py` | Inoreader账号授权工具，首次使用需要运行 |
| `scripts/convert_data_format.py` | 数据格式转换工具，用于迁移历史数据 |
| `scripts/import_results.py` | AI结果导入工具，支持导入外部处理结果 |
| `scripts/manual_process.py` | 手动处理脚本，用于特殊情况的人工干预 |
| `scripts/test_classification.py` | 分类验证工具，测试新闻分类逻辑 |

#### 数据文件
| 文件 | 说明 |
|------|------|
| `_ai_result.json` | AI处理结果文件（手动模式下需要用户创建） |
| `news_data.json` | 新闻数据主存储文件 |
| `upcoming_events.json` | 预告事件数据存储 |

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

### v4.0 (2026-03-28) - 重大架构重构
- ✨ 全新模块化架构，采用工厂模式设计
- ✨ 所有业务逻辑迁移到 `/src` 目录，完全解耦
- ✨ 新增 `main.py` 统一主入口，替代所有旧版脚本
- ✨ 新增 `admin.py` 管理后台入口
- ✨ 新增 `continue_process.py` 断点续处理工具
- 🔧 删除11个冗余旧文件，项目结构大幅精简
- 🔧 优化多数据源协同处理流程
- 🔧 改进去重算法，减少误判

### v3.1 (2026-03-27)
- ✨ 前端排序增强：评级排序时相同评级按时间倒序
- ✨ 支持按类型排序和实体标签点击筛选
- ✨ 新闻分类扩展为12种类型
- 🔧 优化实体识别，过滤通用词汇

### v3.0 (2026-03-18)
- ✨ 新增预告事件追踪功能
- ✨ 支持主动搜索预告事件的新消息
- 🔧 整合 Twitter 和 Inoreader 数据源

### v2.0 (2026-03-11)
- ✨ 新增自动 API 调用模式
- ✨ 扩展关键词库（新增具身智能、RLHF、MoE 等）
- 🔧 优化错误处理和日志

### v1.0
- 初始版本
- RSS 获取与解析
- 关键词预筛选
- AI 处理与去重
- GitHub 推送

## License

MIT
