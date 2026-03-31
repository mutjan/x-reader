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

## Requirements

### Validated
- ✓ RSS新闻抓取（现有功能）
- ✓ 基础去重过滤（现有功能）
- ✓ AI内容处理能力（现有功能）

### Active
- [ ] 多维度选题价值评估（热度、新颖度、领域匹配度）
- [ ] AI自动分类、标签生成、摘要提取
- [ ] 按领域/热度/时间的筛选展示
- [ ] 编辑后台管理功能（信源配置、阈值调整、选题标记）
- [ ] Web界面展示
- [ ] 每小时自动更新机制

### Out of Scope
- 面向普通用户的公开资讯站 - 聚焦内部工具属性
- 内容发布功能 - 仅做选题参考，不直接发布内容
- 社交媒体抓取 - 第一阶段仅处理RSS信源
- 用户账号系统 - 内部使用无需复杂权限

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| 优先服务内部编辑 | 核心用户明确，功能聚焦选题效率提升 | — Pending |
| AI自动评估选题价值 | 减少人工筛选成本，提升判断一致性 | — Pending |
| 每小时更新 | 保证热点时效性，匹配编辑工作节奏 | — Pending |
| 基于现有x-reader迭代 | 复用已有抓取、AI处理能力，减少重复开发 | — Pending |

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
*Last updated: 2026-03-31 after initialization*
