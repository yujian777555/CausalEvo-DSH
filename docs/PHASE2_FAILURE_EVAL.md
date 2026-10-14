# Phase 2.1 Failure Attribution 评估协议（冻结）

日期：2026-10-14。实现：`src/causalevo/analysis/evaluate.py`。

## 1. 指标（冻结）

### Classification（仅在有 ground truth 的子集上计算）

- `accuracy_labeled`：labeled 子集命中率。
- `macro_f1_labeled`：逐类 precision/recall/F1 的宏平均（含 per_class 明细）。

### Attribution quality

- `evidence_coverage_non_unknown`：非 unknown 报告中 ≥1 条 evidence 的比例。
- evidence 正确性：evidence `ref` 必须指向真实 trace 字段（由 schema 校验与测试锁定，见 tests/test_failure_schema.py）。

### Reliability

- `unknown_rate`：unknown 占比。
- `abstention_rate`：弃判占比（本 taxonomy 中等同 unknown_rate，分别列出以备将来细分）。

## 2. 纪律

1. **允许 unknown；不强制分类。** 错误自信比不知道更危险。
2. 指标在看到结果后不得修改；修改需 dated 章节 + Planner 批准。
3. scenario 注入故障标签是构造性 ground truth（engineering evidence），不是模型失败分布的估计；labeled 子集上的 1.0 accuracy 只说明规则链与注入故障对齐，**不得**外推为真实泛化准确率。
4. 离线 fake/replay 数据不用于任何模型能力宣称。

## 3. 当前基线

- B0 raw trace：仅 outcome 映射（timeout/budget_stop→execution，其余 unknown），弃判率高——作为地板基线。
- B1 rule-based：trace_analyzer 规则链。
- 对比只在同一 labeled 子集、同一指标版本上进行。
