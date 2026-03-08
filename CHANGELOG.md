# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
