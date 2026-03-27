# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **前端排序功能增强**
  - 按评级排序时，相同评级内部自动按时间倒序排列（最新内容优先）
  - 表格支持按类型排序
  - 点击实体标签可快速按该实体筛选排序

### Changed
- **新闻分类系统扩展为12种类型**
  - 新增：AI、热点、商业、科研、产品、开源、人物、资本、政策、硬件、航天、其他
  - 优化分类逻辑，提高选题归类准确性

### Fixed
- 修复实体标签中的通用词汇（AI、LLM、X platform等）被错误识别的问题

## [2.0.0] - 2026-03-19

### Added
- **预告事件管理模块 v2.0** (`upcoming_events.py`)
  - 支持关键词分级：核心关键词 vs 辅助关键词
  - 内容相似度验证，防止错误匹配
  - 置信度评分系统（0-1分）
  - CLI 测试工具：`python upcoming_events.py test`
- **统一的更新入口** (`update_news.py`)
  - 整合 Twitter RSS 和 Inoreader 数据源
  - 支持 `--source` 参数选择数据源
  - 支持 `--resume` 恢复中断的处理流程

### Changed
- **重大重构**：清理 18 个冗余文件，项目结构精简
  - 删除废弃脚本：`run_twitter_news.py`, `process_news_local.py` 等
  - 删除过期数据文件
  - 清空并轮转日志文件
- **完善 `.gitignore`**：添加运行时生成的缓存文件、日志、备份等
- **预告事件匹配逻辑改进**：必须匹配至少 1 个核心关键词才能触发

### Fixed
- 修复预告事件错误匹配问题（如 peptides 文章被错误匹配为 Karpathy 播客）
- 移除敏感信息（GitHub Token）从 git 历史

## [1.2.0] - 2026-03-14

### Added
- **Inoreader 数据源支持**：通过 RSS 聚合获取更多科技新闻
- **AI 内容处理**：支持批量处理新闻，生成分级评分（S/A+/A/B）
- **新闻去重功能**：`merge_duplicates.py` 合并相似新闻
- **数据验证工具**：`validate_data.py` 检查数据完整性

### Changed
- 优化 AI prompt 生成逻辑，提高选题质量
- 改进中文标题生成，更符合量子位风格

## [1.1.0] - 2026-03-08

### Added
- 脚本自动生成版本号显示和更新时间逻辑
- AI 驱动的新闻选题筛选和内容生成（使用 Moonshot API）
- 新增 `news_raw_2026-03-08.json` 原始新闻数据文件

### Changed
- 重构项目结构，精简代码
- 实现新的选题规则
- 优化日期显示逻辑，修复 NaN/NaN 日期显示问题

### Fixed
- 修复数据加载错误：恢复 currentDate 元素显示
- 修复 index.html 日期导航按钮问题

## [1.0.0] - 2026-03-06

### Added
- 初始版本发布
- X (Twitter) List Reader 核心功能
- 每日科技新闻摘要展示
- 新闻数据自动更新脚本
- 简洁的暗色主题界面
