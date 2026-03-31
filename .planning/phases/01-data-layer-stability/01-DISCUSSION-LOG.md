# Phase 1: Data Layer Stability - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-03-31
**Phase:** 1-data-layer-stability
**Areas discussed:** 主键机制, 快照机制, 去重逻辑

---

## 主键机制
| Option | Description | Selected |
|--------|-------------|----------|
| 全流程URL主键 | 整个处理流程使用URL作为唯一标识，不依赖列表索引（推荐，彻底解决错位问题） | ✓ |
| 快照索引锁定 | 生成快照后锁定列表索引，AI返回后按索引匹配 | |

**User's choice:** 全流程URL主键，但是注意后续有合并报道同一件事的URL流程，要把合并流程放在每个单一URL处理完之后
**Notes:** 用户明确要求合并流程在单条URL处理完成之后执行，避免影响主键一致性

---

## 快照机制
| Option | Description | Selected |
|--------|-------------|----------|
| JSON格式快照 | 每次处理前将原始新闻列表保存为JSON文件，包含URL、标题等关键信息（推荐） | ✓ |
| 数据库存储 | 将快照信息存入SQLite数据库，方便查询 | |
| 仅内存快照 | 仅在内存中保留，处理完成后丢弃 | |

**User's choice:** JSON格式快照
**Notes:** 无需复杂数据库存储，JSON文件足够满足需求

---

## 去重逻辑
| Option | Description | Selected |
|--------|-------------|----------|
| 保持现有逻辑 | 复用现有URL+标题相似度去重逻辑即可（推荐） | ✓ |
| 增强去重规则 | 需要调整去重阈值或增加新的判断维度 | |

**User's choice:** 保持现有逻辑
**Notes:** 现有去重逻辑已经经过实际验证，不需要调整

---

## Claude's Discretion
- 快照文件的命名规范、存储路径、保留周期等细节
- JSON快照的具体字段结构

## Deferred Ideas
- 数据库存储快照机制
- 去重逻辑规则调整
- 快照自动清理机制
