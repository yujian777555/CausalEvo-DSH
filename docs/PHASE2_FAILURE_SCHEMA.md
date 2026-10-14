# Phase 2.1 Failure Schema（冻结 v1）

日期：2026-10-14。代码唯一事实源：`src/causalevo/analysis/schema.py`。**禁止将模型内部思维链作为 evidence**；evidence 只能指向可观测轨迹事实（事件 seq / ledger 字段 / judge 字段）。

## 1. FailureRecord 结构

```json
{
  "task_id": "micro-000-clamp_value",
  "run_id": "B0-fixed-harness-agent-20261013T084355Z",
  "outcome": "failed",
  "failure_type": "planning_failure",
  "evidence": [{"kind": "no_tool_use", "ref": "ledger.tool_attempts", "detail": "0"}],
  "confidence": "medium",
  "causal_scope": "agent-observable trajectory + judge outcome only",
  "repair_direction": "任务分解应包含定位-修改-验证步骤"
}
```

- `outcome` ∈ success | failed | invalid | timeout | budget_stop。
- `failure_type` ∈ 六类 + `unknown`（abstention 是一等答案）。success 必须不带 failure_type。
- `confidence` ∈ high | medium | low。
- `causal_scope` 声明该归因能/不能声称什么（本版：仅轨迹+judge 结果，无隐藏测试、无 CoT）。
- `repair_direction` 是假设级方向，不是已应用的修复。

## 2. Taxonomy v1（每类：可观测证据 / 隐藏原因假设 / 典型置信）

| 类别 | 可观测证据（evidence） | 隐藏原因假设（不可直接观测） |
|---|---|---|
| planning_failure | 零工具调用但宣称完成；动作顺序与任务矛盾 | 规划器对任务结构的内部建模错误 |
| tool_failure | tool/result 报 Error（unknown tool / not found / access denied）；tool/call 名称不在已知工具集 | 对工具 schema 或环境布局的错误内部模型 |
| knowledge_failure | 编辑已发生、工具无错误，judge 测试仍失败 | 正确修复内容的知识缺口 |
| execution_failure | timeout、provider_error、unknown_cost、墙钟耗尽 | 基础设施而非模型决策问题（必须与模型失败区分） |
| verification_failure | 编辑发生 + judge invalid（语法/import 失败） | 缺少自我验证习惯（无 shell profile 下部分是结构性） |
| strategy_failure | 同一工具同形态调用重复直至预算耗尽 | 探索策略坍塌为单一动作 |
| unknown | 现有轨迹无法区分候选类别 | 未知；不允许强行分类 |

## 3. 归因纪律

1. 基础设施优先：provider/transport/计费故障先归为 execution_failure，绝不记为模型失败。
2. 证据不足必须 `unknown`；错误自信比不知道更危险。
3. evidence 必须可定位到 trace 字段（`ref`），不接受自由文本"模型想到了…"。
4. sealed/hidden 测试内容与 holdout 永不进入 evidence。

## 4. CounterfactualCase（仅结构，P2.1-S6）

`{original_trace, failure_label, candidate_intervention{kind, description}, replay_config{seed, budget_policy}}`；序列化往返由测试锁定；本阶段不执行任何重放提升实验。

## 5. 修订

冻结自 2026-10-14；taxonomy 变更需 dated 章节 + Planner 批准；新增类别必须带可观测证据定义。
