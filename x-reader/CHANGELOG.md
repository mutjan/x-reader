# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [4.0.0] - 2026-03-28

### Added
- **全新模块化架构**
  - 采用工厂模式设计，所有功能解耦为独立模块
  - 新增 `src/` 目录，所有业务代码模块化
  - 支持多种数据源扩展（Fetcher 层）
  - 支持多种处理器扩展（Processor 层）
  - 支持多种发布目标扩展（Publisher 层）
- **管理后台入口** (`admin.py`)
  - 提供系统管理功能入口
  - 支持数据统计、配置管理等
- **断点续处理工具** (`continue_process.py`)
  - 支持中断后恢复处理流程
  - 自动保存处理进度
- **模块化预告事件系统**
  - 整合到主处理流程中
  - 自动事件匹配和状态更新

### Changed
- **主程序重构** (`main.py`)
  - 替代所有旧版主脚本（update_news*.py、run_twitter_news.py等）
  - 支持 `--source` 参数选择数据源（twitter/inoreader/all）
  - 支持手动/自动两种处理模式
  - 统一的工作流程和错误处理
- **项目结构大精简**
  - 删除11个冗余旧脚本文件
  - 根目录仅保留核心入口和配置文件
  - 所有业务逻辑迁移到 `/src` 目录
- **依赖简化**
  - 精简 `requirements.txt`，仅保留必要依赖

### Fixed
- 修复多数据源协同处理问题
- 优化去重算法，减少误判
- 统一数据格式和处理流程

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
