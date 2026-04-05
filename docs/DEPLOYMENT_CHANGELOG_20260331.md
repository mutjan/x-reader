
# 数据层稳定性变更交接文档
**变更日期：** 2026-03-31
**版本：** v5.3
**影响范围：** 全量流水线执行、AI结果导入流程
**变更目的：** 彻底解决历史AI结果匹配错位问题

---

## 一、核心问题解决
**原问题：** AI提示生成后如果RSS feed更新，导入AI结果时会因为列表顺序变化导致索引匹配错位，出现"标题-评分"对应错误。
**解决方案：** 采用"URL唯一主键 + 快照持久化"机制，从根源消除匹配错误。

---

## 二、核心修改点
| 模块 | 修改内容 | 影响 |
|------|----------|------|
| `src/utils/url.py` | 新增统一URL规范化函数，移除所有模块中重复的URL处理逻辑 | 所有模块使用同一套URL规范化规则，消除不一致导致的匹配失败 |
| `src/processors/ai_processor.py` | 1. 生成AI提示时自动保存预处理列表快照<br>2. 移除索引回退逻辑，仅使用URL精确匹配<br>3. 自动清理7天以上的旧快照 | 快照文件自动生成，匹配逻辑更可靠，无需人工清理磁盘 |
| `scripts/import_results.py` | 新增 `--snapshot-id` 参数，支持从快照文件加载原始列表 | 导入时不再重新获取数据，完全不受feed更新影响 |

---

## 三、新的工作流程（重要）
### 完整流水线执行步骤
```mermaid
graph LR
A[执行主流程] --> B[抓取+去重+过滤]
B --> C[生成快照文件 snapshot_{id}.json]
C --> D[生成AI提示文件 ai_prompt_{id}.txt]
D --> E[日志输出 snapshot_id]
F[将提示内容发给AI获取结果] --> G[导入结果时指定 snapshot_id]
G --> H[基于快照精确匹配，100%准确]
```

### 具体命令变化
**原命令：**
```bash
# 生成提示
python main.py --time-window 24h
# 导入结果（会重新获取数据，存在错位风险）
python scripts/import_results.py --result-file ai_result.json
```

**新命令：**
```bash
# 生成提示（自动生成快照，日志输出snapshot_id）
python main.py --time-window 24h
# 导入结果（使用快照ID，不再重新获取数据，完全安全）
python scripts/import_results.py --snapshot-id {snapshot_id} --result-file ai_result.json
```

---

## 四、定时任务Agent注意事项
1. **快照ID获取：** 主流程执行完成后，会在日志中输出 `Snapshot generated: snapshot_{id}.json`，请提取其中的 `{id}` 部分保存
2. **导入参数必填：** 执行导入脚本时必须携带 `--snapshot-id` 参数，否则脚本会提示错误并退出
3. **向后兼容：** 旧的不带 `--snapshot-id` 的导入方式仍然可用，但会有匹配错位风险，不推荐使用
4. **磁盘清理：** 快照文件会自动保存7天，超过时间自动删除，无需人工处理
5. **错误处理：** 如果导入时提示 "Snapshot not found"，请检查快照ID是否正确，或确认快照文件是否已被自动清理

---

## 五、验证方式
执行以下命令验证变更是否正常工作：
```bash
# 执行测试流水线
python main.py --time-window 1h --skip-ai
# 检查是否生成快照文件
ls /tmp/x-reader/snapshot_*.json
# 检查是否生成带snapshot_id的提示文件
ls /tmp/x-reader/ai_prompt_*.txt
```

---

## 六、回滚方案
如果出现兼容性问题需要回滚：
1. 重置代码到上一个版本：`git reset --hard 86c2046`
2. 恢复原导入命令：不再使用 `--snapshot-id` 参数
3. 清理现有快照文件：`rm /tmp/x-reader/snapshot_*.json`

---

## 七、联系方式
如有问题请联系开发团队。
