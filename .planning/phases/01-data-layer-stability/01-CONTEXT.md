# Phase 1: Data Layer Stability - Context

**Gathered:** 2026-03-31
**Status:** Ready for planning

<domain>
## Phase Boundary

解决历史数据一致性问题，构建稳定的数据基础。本阶段聚焦底层数据处理的稳定性，解决历史上出现的AI结果匹配错位问题，为后续AI处理和上层功能提供可靠的数据保证。

</domain>

<decisions>
## Implementation Decisions

### 主键机制
- **D-01:** 全流程使用URL作为唯一主键，不依赖列表索引，彻底解决AI结果匹配错位问题
- **D-02:** 同源新闻合并流程放在每个单一URL处理完成之后执行，不影响单条新闻的主键一致性

### 快照机制
- **D-03:** 每次处理前将原始新闻列表保存为JSON格式快照，包含URL、标题、来源、发布时间等关键信息
- **D-04:** AI处理过程中严格按照URL匹配结果，不使用列表索引

### 去重逻辑
- **D-05:** 保持现有去重逻辑不变，继续使用URL标准化+标题相似度的去重策略
- **D-06:** 去重流程在快照生成后、AI处理前执行，保证进入AI处理的新闻列表是稳定的

### Claude's Discretion
- 快照文件的命名规范、存储路径、保留周期等细节由开发团队决定
- JSON快照的具体字段可以根据实际需要调整，只要保证URL作为主键即可

### Folded Todos
无
</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### 核心代码
- `src/models/news.py` — 新闻数据模型，包含RawNewsItem.get_unique_id()方法
- `src/processors/duplicate.py` — 新闻去重模块，现有去重逻辑实现
- `src/fetchers/base.py` — 抓取器基类
- `src/config/settings.py` — 配置文件

### 问题背景
- 历史问题：标题-链接错位问题（已在2026-03-28修复的v5.3版本说明
</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `RawNewsItem.get_unique_id()` — 已实现基于URL的唯一ID生成
- `DuplicateRemover` — 已实现基于URL标准化的去重逻辑
- `normalize_url()` — URL标准化工具函数

### Established Patterns
- 新闻处理流程：抓取 → 去重 → AI处理 → 合并 → 存储
- 数据存储使用按日期分组的JSON格式

### Integration Points
- 快照机制需要嵌入现有抓取流程之后，去重流程之前
- 主键机制需要在AI处理输入和结果匹配阶段使用
</code_context>

<specifics>
## Specific Ideas

- 历史上发生过的匹配错位问题是因为抓取和AI处理之间feed更新，导致列表顺序变化，通过URL主键可以100%解决这个问题
- 合并流程在单条处理完成之后，这样同源新闻的多个URL都能得到完整的AI处理结果后再合并
</specifics>

<deferred>
## Deferred Ideas

- 数据库存储快照 — 暂时不需要，JSON格式足够满足需求
- 去重逻辑优化 — 现有逻辑已经足够稳定，不需要调整
- 快照清理机制 — 后续阶段再考虑实现自动清理过期快照

### Reviewed Todos (not folded)
无
</deferred>

---

*Phase: 01-data-layer-stability*
*Context gathered: 2026-03-31*
