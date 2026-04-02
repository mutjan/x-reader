# 科技新闻选题聚合系统

## What This Is
一个面向内部编辑的科技新闻选题聚合系统，自动从RSS源获取科技新闻，通过AI评估筛选高价值选题，按领域和热度分类展示，帮助编辑团队快速发现优质报道线索。

## Core Value
**自动发现高价值科技选题，降低编辑信息搜集成本，提升选题效率和质量。**

## Context
- **目标用户**：内容编辑团队
- **使用场景**：日常选题会、热点追踪、行业动态监测
- **现有基础**：基于已有x-reader代码库迭代开发
- **更新频率**：每小时自动抓取更新

## Current Milestone: v2.0 同事件新闻分组功能重构

**Goal:** 重新实现同事件新闻自动分组，将分组信息存储在独立JSON文件，前端聚合展示同事件新闻，不修改原有news data.json结构。

**Target features:**
- 在现有处理流程中移除同事件新闻合并逻辑（原来会合并成一条，现在保留每条独立）
- 新增独立新闻组JSON文件存储分组关系（组ID → 包含的新闻ID列表）
- 前端将同一组内的多条新闻聚合展示为事件时间线
- 原news data.json结构保持不变，每条新闻仍然独立存储

## Requirements

### Validated (v1.0 + phase 07 completed)
- ✓ RSS新闻抓取（现有功能）
- ✓ 基础去重过滤（现有功能）
- ✓ AI内容处理能力（现有功能）
- ✓ 多维度选题价值评估（热度、新颖度、领域匹配度）
- ✓ AI自动分类、标签生成、摘要提取
- ✓ 按领域/热度/时间的筛选展示
- ✓ 编辑后台管理功能（信源配置、阈值调整、选题标记）
- ✓ Web界面展示
- ✓ 每小时自动更新机制
- ✓ 移除处理流程中的同事件新闻合并逻辑 - Validated in Phase 07: cleanup-existing-merge-logic

### Active (v2.0)
- [ ] 新增独立新闻组JSON文件存储分组关系
- [ ] 前端聚合展示同事件新闻为时间线
- [ ] 保持原有news_data.json结构不变

### Out of Scope
- 面向普通用户的公开资讯站 - 保持内部工具属性
- 内容发布功能 - 仅提供选题线索，不涉及内容生产
- 社交媒体内容抓取 - v1已支持Twitter RSS，v2不扩展
- 全文内容存储 - 仅存储元数据，避免版权风险
- 智能写稿功能 - 聚焦选题发现，不涉及内容生成

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 优先服务内部编辑 | 核心用户明确，功能聚焦选题效率提升 | v1.0 - Implemented |
| AI自动评估选题价值 | 减少人工筛选成本，提升判断一致性 | v1.0 - Implemented |
| 每小时更新 | 保证热点时效性，匹配编辑工作节奏 | v1.0 - Implemented |
| 基于现有x-reader迭代 | 复用已有抓取、AI处理能力，减少重复开发 | v1.0 - Implemented |
| URL作为唯一主键 | 彻底解决AI结果匹配错位问题 | v1.0 - Implemented |
| 两步AI处理流程 | 避免LLM API成本，提供完整人工控制 | v1.0 - Implemented |
| JSON文件存储 | 保持架构轻量，无需数据库依赖 | v1.0 - Implemented |
| **独立分组文件方案** | 不改变原有新闻数据结构，减少对现有流程影响 | v2.0 - Planned |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd:transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd:complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-02 after Phase 07 completion*
