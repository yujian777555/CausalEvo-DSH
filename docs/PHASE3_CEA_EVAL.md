# Phase 3.1 CEA 评估协议（冻结）

日期：2026-10-14。实现：scripts/run_cea_simulation.py。

## 1. 指标（冻结）

### Intervention Selection
- top-1 selection accuracy：选中动作 == 该状态 oracle 最优动作（重放矩阵中 reward 最大者）。
- successful intervention rate：选中动作的 success_delta > 0 的比例。

### Learning
- cumulative reward（全程）。
- regret：oracle reward − 所选 reward 的累计/均值。
- learning curve：逐 episode reward 与累计 regret（learning_curve.json）。

### Efficiency
- intervention cost：cost_delta_cny（合成计量）入 ledger 对比。
- additional actions：由 cf_ledger.provider_attempts − original 得出。

### Generalization
- 时间切分：rounds 0–6 训练更新，rounds 7–9 只评估不更新；指标只在评估窗报告。

## 2. 基线与消融（冻结）

- B0 random（seed 固定）、B1 rule（taxonomy 映射）、B2 CEA-v0（LinUCB）。
- A1 无历史 vs A2 有历史特征；A3 普通 outcome 奖励 vs A4 因果差值奖励。

## 3. 纪律

1. 指标在看到结果后不得修改（修订需 dated 章节 + Planner 批准）。
2. 所有数字来自重放矩阵查表；不声称真实模型改善。
3. 状态空间仅 6 个失败态 —— 结果为管线验证，功效说明见 PHASE3_CEA_RESULTS.md。
