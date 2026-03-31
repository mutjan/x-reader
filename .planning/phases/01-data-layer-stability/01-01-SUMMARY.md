---
phase: 01-data-layer-stability
plan: 01
subsystem: data-layer
tags: [url-normalization, snapshot, data-stability]
requires: []
provides: ["统一URL规范化工具", "AI处理快照机制"]
affects: ["去重逻辑", "ID生成逻辑", "AI处理流程"]
tech-stack:
  added: ["src/utils/url.py"]
  patterns: ["统一工具函数", "快照持久化"]
key-files:
  - src/utils/url.py (new)
  - src/models/news.py
  - src/processors/duplicate.py
  - src/processors/ai_processor.py
  - src/config/settings.py
decisions:
  - URL规范化逻辑集中在单独模块，避免多实现不一致
  - 快照使用内容哈希作为ID，保证相同输入生成相同ID
  - 快照存储在临时目录，不污染主数据目录
metrics:
  duration: 10 minutes
  completed_date: 2026-03-31
  tasks: 2
  files: 5
---

# Phase 01 Plan 01: 数据层基础能力加固 Summary

**One-liner:** 实现了统一URL规范化机制和AI处理快照功能，解决了URL处理不一致问题，建立了数据溯源基础。

## Deviations from Plan

None - plan executed exactly as written.

## Verification Results

### 1. URL规范化功能 ✅
- 测试用例全部通过，支持以下规范化规则：
  - 移除URL锚点和跟踪参数（utm_*, ref等）
  - 统一HTTP/HTTPS协议为HTTPS
  - 移除www子域前缀
  - 统一URL路径为小写
  - 移除末尾斜杠
- 所有模块（ID生成、去重）均调用同一个normalize_url函数，保证一致性

### 2. 快照生成功能 ✅
- 生成8位内容哈希作为快照ID
- 快照包含完整的预处理条目信息、创建时间、数量统计
- 快照文件保存在.snapshots目录
- AI提示词文件名包含快照ID，建立关联关系
- 日志输出快照ID方便用户后续查找

### 3. 现有功能验证 ✅
- 重复内容移除功能正常工作：相同URL不同参数会被识别为重复
- 测试用例中两条URL不同但内容相同的条目被正确去重为1条

## Known Stubs

None - all features fully implemented.

## Self-Check: PASSED
- [x] src/utils/url.py 存在并导出normalize_url函数
- [x] news.py和duplicate.py均调用新的规范化函数
- [x] ai_processor.py包含快照生成逻辑
- [x] settings.py添加了SNAPSHOT_DIR配置
- [x] 所有测试用例通过
