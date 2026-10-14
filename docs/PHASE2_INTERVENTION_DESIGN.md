# Phase 2.3 Intervention + Counterfactual Replay 设计

日期：2026-10-14。范围：Failure-aware Intervention 与配对反事实重放。**不实现** Evolution Controller / RL / Prompt Evolution / 自动搜索。

## 1. 链路与组件

```
DiagnosisResult (P2.2)
  │  rules only (no LLM)
  ▼
CandidateIntervention (src/causalevo/intervention/)
  │  tape_transform 绑定
  ▼
Counterfactual replay (src/causalevo/counterfactual/replay.py)
  │  同任务 / 同磁带 / 同预算 / 容器世界 / 独立 judge
  ▼
CounterfactualResult（original vs intervened）
```

## 2. Intervention taxonomy

| 类型 | 目标失败 | 机制（required_change） | 磁带变换 |
|---|---|---|---|
| tool_intervention | tool_failure | 调用前校验工具名/参数 | replace_unknown_tool_with_read |
| planning_intervention | planning_failure | 先出 定位→修改→验证 计划 | prepend_read_step |
| verification_intervention | verification_failure | 写入后 read-back 并修正 | append_readback_and_fix |
| strategy_intervention | strategy_failure | 同工具重复 N 次后强制切换 | break_repeat_with_read |
| knowledge_intervention | knowledge_failure | 追加错误定位上下文 | inject_fix_after_write |
| no_intervention | unknown/any | 不变 | identity |

## 3. Replay 机制（诚实边界）

- 干预以对 provider 磁带的**确定性变换**实现（纯函数，不改原磁带）；两臂都经过真实 DSH runtime（容器）+ 独立 judge。
- 变换是干预机制的**模拟**：例如"校验工具名"的模拟 = 把非法工具调用替换为合法 read。改进的 counterfactual 结果证明的是"机制在该模拟下端到端工作"，**不是**真实模型会改善的证据。
- 预算：replay 包络（8 provider calls / 4096 output / 12 tool / 240s）四臂一致并记录于 manifest；与冻结的 B0/B1 实验包络（2/2048/20/300）是不同配置，文档明确分离。
- 原始磁带永不修改（apply_tape_transform 为纯函数，测试锁定）。

## 4. 三个 Replay Case（对应计划 S3）

1. case_tool（tool_failure）：`bad_tool_blocks_write`——坏工具调用挤掉了 write 前必需的 read，write 被运行时拦截；干预后 read 恢复，write 生效。
2. case_verification（verification_failure）：`broken_write`——写入语法错误代码后直接结束；干预后 read-back + 修正写入。
3. case_ineffective（对照）：`wrong_fix`（knowledge_failure）+ strategy 干预（无重复循环，变换为空）→ 预期无改善。

## 5. 已知限制

- 模拟干预 ≠ 真实干预效果；live 验证需单独授权与计划。
- 案例集小（3 类 × 2 任务 × 4 臂 = 24 次配对运行），统计仅描述性。
- B1 随机臂由 seed 固定选择，可能恰好选中有效干预（如实记录）。
