# x-reader 新闻聚合工具 v1.0.0

从 Twitter RSS 和 Inoreader API 自动获取科技新闻，通过 AI 筛选和加工，生成适合科技媒体发布的选题。

## 架构重构说明

本版本进行了全面的模块化重构，将原来的单文件架构拆分为多个独立模块，提高了可维护性和扩展性：

```
src/
├── config/          # 配置管理模块
│   └── settings.py  # 统一配置项
├── fetchers/        # 数据获取模块
│   ├── base.py      # 抽象基类
│   ├── twitter_fetcher.py    # Twitter RSS获取器
│   ├── inoreader_fetcher.py  # Inoreader API获取器
│   └── factory.py   # Fetcher工厂类
├── models/          # 数据模型模块
│   └── news.py      # 新闻数据结构和实体标准化
├── processors/      # 处理模块
│   ├── filter.py    # 关键词预筛选
│   ├── duplicate.py # 去重处理
│   └── ai_processor.py  # AI处理模块
├── publishers/      # 发布模块
│   ├── base.py      # 抽象基类
│   ├── github_pages.py  # GitHub Pages发布器
│   └── factory.py   # Publisher工厂类
└── utils/           # 工具函数模块
    ├── common.py    # 通用工具函数
    └── auth.py      # 认证工具
```

## 功能特性

- **多数据源支持**: 支持 Twitter RSS 和 Inoreader API 两种数据源
- **模块化架构**: 各模块职责清晰，易于扩展新的数据源和发布渠道
- **智能预筛选**: 基于关键词库自动筛选高价值新闻
- **多维度去重**: 基于URL、标题相似度、内容相似度的多层去重机制
- **AI智能处理**: 支持自动和手动两种处理模式，生成标准化的新闻选题
- **自动发布**: 自动同步到 GitHub Pages
- **配置与代码分离**: 所有配置集中管理，支持环境变量覆盖

## 快速开始

### 1. 安装依赖

```bash
pip3 install -r requirements.txt
```

### 2. 配置环境变量（可选）

```bash
# Inoreader 认证信息（可选，默认已内置）
export INOREADER_CLIENT_ID="your_client_id"
export INOREADER_CLIENT_SECRET="your_client_secret"
```

### 3. Inoreader 授权（首次使用需要）

```bash
python3 auth_inoreader.py
```

按照提示在浏览器中完成OAuth授权流程。

### 4. 运行主程序

```bash
# 全量更新（所有数据源）
python3 main.py

# 只更新Twitter
python3 main.py --source twitter

# 只更新Inoreader
python3 main.py --source inoreader

# 获取最近48小时的新闻
python3 main.py --time-window 48

# 测试模式（只获取数据不处理）
python3 main.py --test

# 处理但不发布
python3 main.py --no-publish
```

## 配置说明

所有配置集中在 `src/config/settings.py` 中，可以直接修改或通过环境变量覆盖：

### 数据源配置
- `RSS_CONFIG`: 配置Twitter和Inoreader的连接信息
- `PRIORITY_KEYWORDS`: 优先级关键词库，匹配到的新闻会获得更高分数
- `BLACKLIST_KEYWORDS`: 黑名单关键词，匹配到的新闻会被直接过滤

### 分级配置
- `GRADE_THRESHOLDS`: 新闻分级阈值（S/A+/A/B/C）
- `NEWS_TYPES`: 支持的新闻类型列表

### 文件路径配置
- `DATA_FILE`: 新闻数据存储文件
- `PROCESSED_IDS_FILE`: 已处理ID缓存文件
- `AUTH_PROFILES_FILE`: 认证信息存储路径

## 扩展开发

### 添加新的数据源

1. 在 `src/fetchers/` 下创建新的Fetcher类，继承自 `BaseFetcher`
2. 实现 `fetch()` 和 `test_connection()` 方法
3. 在 `src/fetchers/factory.py` 中注册新的Fetcher类型

### 添加新的发布渠道

1. 在 `src/publishers/` 下创建新的Publisher类，继承自 `BasePublisher`
2. 实现 `publish()` 和 `test_connection()` 方法
3. 在 `src/publishers/factory.py` 中注册新的Publisher类型

### 自定义AI处理逻辑

1. 在 `src/processors/ai_processor.py` 中继承 `BaseAIProcessor`
2. 实现 `process_batch()` 方法
3. 在主程序中使用自定义的处理器

## 命令行参数说明

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--source` | 数据源类型：twitter/inoreader/all | all |
| `--time-window` | 获取最近多少小时内的新闻 | 24 |
| `--min-score` | 预筛选最低得分 | 10 |
| `--batch-size` | AI处理批量大小 | 30 |
| `--no-publish` | 不发布到GitHub Pages | False |
| `--test` | 测试模式，只获取数据不处理 | False |

## 项目结构说明

### 核心模块

1. **配置模块 (`config`)**：集中管理所有配置项，支持环境变量覆盖
2. **数据获取模块 (`fetchers`)**：统一的数据源接口，支持多种数据源扩展
3. **数据模型模块 (`models`)**：定义标准化的数据结构，提供实体标准化功能
4. **处理模块 (`processors`)**：包含筛选、去重、AI处理等核心逻辑
5. **发布模块 (`publishers`)**：统一的发布接口，支持多种发布渠道
6. **工具模块 (`utils`)**：通用工具函数，提供日志、JSON处理、日期解析等功能

### 优势

- **高内聚低耦合**：各模块职责单一，修改一个模块不会影响其他模块
- **易于测试**：每个模块都可以独立单元测试
- **易于扩展**：添加新功能只需要添加对应的模块，不需要修改核心逻辑
- **代码复用**：公共逻辑被提取到工具模块，避免重复代码
- **可维护性**：代码结构清晰，便于理解和维护

## 升级指南

从旧版本升级：

1. 备份原有数据文件：`news_data.json`, `.processed_ids.json`
2. 运行新的主程序：`python3 main.py`
3. 首次运行会自动兼容旧有数据格式

## 许可证

MIT License
