# CE-DSH-P4-R1.10 — 算法真实性修正（Algorithm Fidelity）

日期：2026-10-26。本文件与 `docs/PHASE4_R1_9_CORRECTION_ADDENDUM.md`、`docs/PHASE4_R1_9_RECONCILIATION.md` 共同构成对 R1.9 的更正，**不追溯改写历史数据**。

## 1. NSGA-III 在 live pilot 中实际调用了几次？——**0 次**

源码事实（`src/causalevo/evolution/online_evolution.py::_evolve`）：

- 父代选择条件：`len(measured) > n_parents`（n_parents = min(4, len(measured))）。R1.9 唯一 evolve 事件时 `len(measured)=4` → 不满足条件 → **全部直接成为父母**，`nsga3_select` 未调用。
- 种群从 4 增至 8（max_population=16），无溢出 → 幸存者选择分支也未调用。

因此 R1.9 的 live 演化只做了**交叉、变异与种群版本更新**，不能称为验证了 NSGA-III。`docs/PHASE4_FORMAL_EXPERIMENT_REPORT.md` 的相关表述由 `docs/PHASE4_R1_9_CORRECTION_ADDENDUM.md` 正式更正。

**遥测口径**：历史 evolve 事件本身**不含**新加入的调用计数字段（计数器在实验后加入）；零调用是**依据归档源码分支条件与归档控制器状态重建的**，不是运行当时输出的计数。新计数器只影响未来事件；历史投影未添加合成计数。

**现在的可核查证据**：evolve 事件包含 `nsga3_parent_selection_calls` 与 `nsga3_survivor_selection_calls` 两个字段（`online_evolution.py`），并有回归测试：

- `test_nsga3_parent_selection_not_called_with_exactly_four_measured`（4 已测量无溢出 → 0 调用，正是 R1.9 情形）
- `test_nsga3_parent_selection_called_with_more_than_four_measured`（>4 → 1 调用）
- `test_nsga3_survivor_selection_called_on_overflow`（溢出 → 幸存者调用）

离线 `tests/test_nsga3.py`、`test_evolution_e2e.py` 继续独立验证 NSGA-III 实现。

## 2. CEA-v2.1：干预增量成本/调用（修正后契约）

`run_row`（`scripts/run_phase4_r19_pilot.py`）现在：

1. attempt 1 结束后立即快照 `calls_after_1` 与 `cost_after_1`。
2. attempt 2 结算后只将**增量**传给 `observe()`：`attempt_2_cost_cny = known_cost_cny − cost_after_1`、`attempt_2_provider_requests = provider_attempts − calls_after_1`。
3. 行记录同时保留每次 attempt 的成本/调用与总量（`attempt_1_cost_cny`、`attempt_2_cost_cny`、`attempt_1_provider_requests`、`attempt_2_provider_requests`）。
4. 控制器版本更新为 **`cea-v2.1-r1.10`**，使未来实验不会把旧整-episode 成本语义与增量语义混淆。

**R1.9 的历史观察不追溯改写**（它们用的是旧整-episode 口径，已在附注中披露）。

## 3. no-op 选择的显式反馈

`genome_to_text()` 为 None 时（空/no-op 表型）：不再提前无反馈返回，而是**不重试、但恰好观察一次**，记录最终失败与 **0 增量成本/0 增量调用**（不额外发模型请求）。基础设施/未知费用结局仍只记为 infra，绝不进入行为奖励。

测试（`tests/test_incremental_fitness.py`，4/4）：

- 增量成本排除 attempt-1（`cand.costs == attempt_2_cost_cny`，不等于总成本）。
- no-op 恰好测量一次（`cand.n == 1`、`cand.costs == 0`、`cand.calls == 0`、`retried == False`）。
- infra 不进入行为统计（`cand.n == 0`）。
- 同一事件日志重放到同一控制器状态（`state_dict` 人口、n/successes/costs/calls 一致）。

## 4. 对 R1.9 结果语义的影响

- R1.9 的"1 次演化步骤"应理解为**种群更新事件**（非 NSGA-III 选择事件）。
- CEA-v2 的在线更新链条（select→observe→evolve→选择变化）仍然真实存在，但其**成本目标在 R1.9 中被整-episode 成本稀释**（第一次尝试成本因任务而异）。这一局限已记录，不影响"无提升证据"的统计结论（该结论基于成功率，与成本目标定义无关）。
- R1.10 的 CEA-v2.1 只影响**未来**实验的适应度口径，不产生新的真实 API 结果（本轮 0 调用、¥0）。
