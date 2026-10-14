# Phase 2.3 Intervention 结果（离线，零费用）

日期：2026-10-14。全部运行于容器世界 + fake provider 磁带；**磁带变换是对干预机制的模拟，不是真实模型改善的证据**。

## 1. 案例矩阵与配对结果

3 案例 × 2 任务 × 4 臂 = 24 次配对重放（`results/phase2/intervention/counterfactual_results.jsonl`）。

| 案例 | 场景（注入故障） | 干预 | 预期 | 实测 |
|---|---|---|---|---|
| case_tool | bad_tool_blocks_write（tool_failure：坏工具调用挤占 write 前必需的 read） | 工具校验（变换：未知工具→read） | 解锁 write | 改善（B2/B3 两臂均 False→True） |
| case_verification | broken_write（verification_failure：写入语法错误即结束） | 强制自测（变换：read-back + 修正写入） | 捕获并修正 | 改善 |
| case_ineffective（对照） | wrong_fix（knowledge_failure） | 错配 strategy 干预（变换为空操作） | 无改善 | 无改善 ✓ |

## 2. 臂间对比（baseline_comparison.json）

| 臂 | cases | improved | no_change | regressed | cost_delta_cny（合成计量） |
|---|---|---|---|---|---|
| B0 无干预 | 6 | 0 | 6 | 0 | 0 |
| B1 随机干预 | 6 | 2 | 4 | 0 | 0.00102 |
| B2 规则干预 | 6 | 4 | 2 | 0 | 0.00107 |
| B3 诊断引导 | 6 | 4 | 2 | 0 | 0.00107 |

- B0 恒零改善（identity 完整性验证通过）。
- B1 随机臂按 seed 选到两次有效变换（如实记录：随机臂偶尔有效正是它存在的意义——证明"不是任何修改都有用"需要对照）。
- B2/B3 在机制匹配的案例改善、对照案例不变；Intervention Gain（非 B0 臂）：P(success|intervention)−P(success|original) = 见 baseline_comparison.json。
- cost_delta 为 fake 磁带合成计量（每次调用固定合成 usage），仅证明记账链路，不对应真实费用。

## 3. 反虚假因果控制（S6 落实）

- 配对：同任务、同磁带、同预算包络、仅变换不同。
- 每案例记录 changed_steps（磁带差异）、双臂 ledger、替代干预（B1 随机臂）对照。
- 对照案例证明错配干预无效果；若对照改善则实验设计有误（本轮未发生）。

## 4. 产物

- results/phase2/intervention/{intervention_manifest.json, counterfactual_results.jsonl, baseline_comparison.json, sample_cases.json}
- 文档：docs/PHASE2_INTERVENTION_DESIGN.md、docs/PHASE2_INTERVENTION_EVAL.md

## 5. 限制

1. 模拟干预不证明真实模型改善；需 live pilot 另行验证（未授权）。
2. 规模小（24 配对），统计仅描述性。
3. 磁带合成计量与真实价格无关。
