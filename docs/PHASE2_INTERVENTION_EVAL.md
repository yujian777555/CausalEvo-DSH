# Phase 2.3 Intervention 评估协议（冻结）

日期：2026-10-14。实现：scripts/run_intervention_eval.py + src/causalevo/counterfactual/。

## 1. 指标（冻结）

### Outcome

- success improvement：干预臂任务成功数 - 原始臂成功数（按 case 配对）。
- failure reduction：counterfactual_outcome 从非 success 转为 success 的比例。

### Efficiency

- intervention cost：干预臂相对原始臂的 `known_cost_cny` 差（cost_delta_cny；fake provider 下为合成计量，仅作管线证据）。
- extra steps：干预臂相对原始臂的 provider/tool 调用增量（ledger 对比）。

### Reliability

- confidence：干预置信的定性级别（schema 字段）。
- abstention：诊断 unknown 时生成 no-op 干预（不强行干预）。

### Causal metrics（重点）

- Intervention Precision：诊断引导的干预中命中真实注入故障类别且 success 改善的比例。
- Intervention Gain：`P(success | intervention) − P(success | original)`，仅在配对样本上计算。
- 配对设计：同任务、同基础磁带、同预算包络、仅磁带变换不同。

## 2. 反虚假因果纪律（S6）

1. 禁止从"干预后成功"直接推出"干预导致成功"；必须配对比较且记录 changed_steps。
2. 每案例记录：original trace 结果、changed_steps（磁带差异）、预算差、以及替代干预（B1 随机臂）作为对照。
3. 磁带变换是对干预机制的**模拟**；真实模型效果需要 live pilot 另行验证。
4. replay 随机性：fake provider 完全确定；live 阶段的 provider 随机性另行记录（本阶段无）。

## 3. Baseline 臂（冻结）

- B0 no intervention：identity 重放，success_delta 恒应为 0。
- B1 random：从干预库随机选（seed 20261014）。
- B2 rule：注入故障真值 → 规则映射。
- B3 diagnosis-guided：RuleDiagnoser → InterventionGenerator。
