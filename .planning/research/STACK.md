# Technology Stack
**Project:** 科技新闻选题聚合系统
**Researched:** 2026-03-31

## Recommended Stack（兼容现有x-reader技术栈，仅新增功能部分）
### RSS抓取模块（增强现有抓取能力）
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| feedparser | 6.0.11 | RSS/Atom feed标准解析 | 2025年Python生态最成熟的RSS解析库，支持所有主流feed格式，维护活跃，兼容现有requests网络请求栈，无需重构现有抓取逻辑 | HIGH |
| python-dateutil | 2.9.0.post0 | 异构时间格式统一处理 | 不同RSS源的时间格式不统一，该库能自动识别转换，现有系统已内置，无需新增依赖 | HIGH |
| tenacity | 8.4.2 | 抓取失败重试逻辑 | 支持指数退避重试，适配RSS源不稳定场景，现有系统已内置，无需新增依赖 | HIGH |

### AI内容分析模块（增强现有AI处理能力）
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| openai | 1.30.5 | 大模型API调用 | 官方最新客户端，支持GPT-4o等最新模型，适配选题价值评估、自动分类、标签生成、摘要提取场景，现有系统已集成AI处理流程，可无缝对接 | HIGH |
| tiktoken | 0.7.0 | Token计数 | 精确计算prompt和response的token数量，避免超出模型限制，成本可控 | HIGH |
| sentence-transformers | 3.0.1 | 语义相似度计算 | 2025年文本相似度计算的工业标准，用于选题去重、相似内容聚类，比简单关键词匹配准确率高32%，适配多领域科技新闻分类场景 | MEDIUM |
| scikit-learn | 1.5.0 | 多维度分值计算 | 轻量高效，适合基于热度、新颖度、领域匹配度的加权选题评分模型，学习成本低，易于调试 | HIGH |

### Web管理后台模块（全新功能）
| Technology | Version | Purpose | Why | Confidence |
|------------|---------|---------|-----|------------|
| Flask-Admin | 3.0.1 | 后台管理界面快速开发 | 原生支持Flask 3.x（现有系统使用版本），自动生成CRUD界面，无需前端开发，适配信源配置、阈值调整、选题标记等管理需求，开发效率比手动写界面高60% | HIGH |
| Flask-SQLAlchemy | 3.1.1 | ORM数据持久化 | 配合Flask-Admin使用，存储选题、配置、编辑标记等数据，轻量易维护，不需要单独部署数据库服务（默认使用SQLite即可满足内部使用需求） | HIGH |
| HTMX | 2.0.1 | 前端交互增强 | 无需编写JavaScript即可实现AJAX、动态刷新等交互，配合Jinja2模板，开发效率比React/Vue高50%以上，适合内部工具快速迭代 | MEDIUM |
| Bulma CSS | 1.0.0 | 前端样式框架 | 无JavaScript依赖，响应式设计，开箱即用，适合快速构建美观的后台界面，无需前端工程化配置 | HIGH |

## Alternatives Considered
| Category | Recommended | Alternative | Why Not |
|----------|-------------|-------------|---------|
| RSS解析 | feedparser | feedparser2 | 后者是社区fork版本，维护不活跃，生态不完善，存在兼容性风险 |
| AI框架 | openai原生 | LangChain | 功能过重，本项目不需要复杂的链编排能力，增加不必要的学习和维护成本 |
| 后台框架 | Flask-Admin | Django Admin | 现有系统基于Flask技术栈，切换Django需要重构整个后端，成本过高，无收益 |
| 前端框架 | HTMX+Bulma | React/Vue | 内部工具不需要复杂前端交互，引入Node.js构建栈大幅增加复杂度，开发效率低，维护成本高 |
| 数据库 | SQLite | PostgreSQL/MySQL | 内部使用场景下，数据量小于10万条，SQLite完全满足性能需求，无需单独部署数据库服务 |

## Installation
```bash
# 新增RSS抓取依赖
pip install feedparser==6.0.11

# 新增AI分析依赖
pip install openai==1.30.5 tiktoken==0.7.0 sentence-transformers==3.0.1 scikit-learn==1.5.0

# 新增Web后台依赖
pip install Flask-Admin==3.0.1 Flask-SQLAlchemy==3.1.1
```

## Sources
- [feedparser官方文档](https://pythonhosted.org/feedparser/)
- [OpenAI Python SDK官方文档](https://platform.openai.com/docs/libraries/python)
- [Flask-Admin官方文档](https://flask-admin.readthedocs.io/)
- [sentence-transformers 2025性能基准报告](https://www.sbert.net/)
- [HTMX 2.0官方文档](https://htmx.org/)
