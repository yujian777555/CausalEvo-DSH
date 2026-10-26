# CE-DSH-P4-R1.9 — 更正附注（Dated Correction Addendum）

日期：2026-10-26。本附注对 `docs/PHASE4_FORMAL_EXPERIMENT_REPORT.md` 作必要更正，**不改写任何历史结果、行记录或账本**。

## 1. 证据包此前不完整

此前 GitHub 包只含 `analysis.json`、`controller_state.json`、`manifest.json` 与 proxy-ledger 控制文件，**缺少原始 `tasks.jsonl`、`events.jsonl`、`proxy-ledger/ledger.jsonl`**（被 `.gitignore` 的 `*.jsonl` 规则吞没），因此无法独立复算。

**更正**：已从本机原始文件生成并提交脱敏投影（`results/phase4/r19-audit/`）：208 行任务记录、控制器事件、全轮请求账本，以及 `manifest_reconciled.json`（源文件与投影哈希、逐 request_id 终态、每 run 与全轮费用）。原始文件哈希见 `docs/PHASE4_R1_9_RECONCILIATION.md`。

## 2. manifest 行数口径错误

`manifest.json` 的 `rows=58` 与 `analysis.json` 的 `rows_total=208` 不一致。原因是 runner 的 `rows` 变量只统计**最后一个续跑进程**新执行的行数，字段名未披露该语义。

**更正**：明确 `rows_total=208`（全部配对行），`rows_written_last_process=58`（最后进程新执行数）。原始 manifest 字节与哈希保留（`c941c40b…`），`manifest_reconciled.json` 以明确字段修正。

## 3. 请求总数需要对账（现已完成）

- 总 SETTLED 请求 = 912（24+2+13+180+693，唯一 request_id 终态）。
- 行级 provider_calls = 699，与 final run SETTLED 693 的差 6 = **micro-011-second_largest/B1-random 中止行的 1 UNKNOWN + 5 REJECTED**（该 scope SETTLED=0，行级尝试=6）。
- 全轮费用 = 1.306339（SETTLED，peak）+ 0.157041（UNKNOWN 上界）= **1.463380 CNY < 2.00**。
- 最终 run 的 `settled_cost_cny=0.9948804852` 是该 run 的 693 请求费用，与全轮合计 1.306339 属不同口径。

详见 `docs/PHASE4_R1_9_RECONCILIATION.md`。

## 4. **R1.9 实际并未调用 NSGA-III 选择**（重要更正）

原报告称"1 次 NSGA-III 演化步骤"。经源码与控制器状态复核：唯一一次 live evolve 事件中有 **4 个已测量候选 + 4 个后代，max_population=16**：

- 父代选择：`n_parents = min(4, len(measured)) = 4`，`len(measured) = 4` 不大于 `n_parents`，因此 **全部 4 个已测量候选直接成为父母**，`nsga3_select` **未被调用**。
- 种群从 4 增至 8（未超 16），**未触发溢出幸存者选择**，因此幸存者分支的 `nsga3_select` 也未被调用。

**结论**：live pilot 实际执行的是**交叉、变异与种群版本更新**，其唯一演化事件**没有调用 NSGA-III 选择（0 次）**。不得称该 pilot 验证了 NSGA-III 或其贡献。离线 `tests/test_nsga3.py`、`test_evolution_e2e.py` 等独立测试仍验证 NSGA-III 实现本身，不与此矛盾。

**计数口径澄清（R1.11 补充）**：R1.9 的历史 evolve 事件**不含** `nsga3_parent_selection_calls` / `nsga3_survivor_selection_calls` 字段——这些计数器是在实验之后才加入代码的。因此"0 次调用"是**依据归档源码的分支条件（4 已测量候选 → 4 父母、无溢出）与归档控制器状态重建的事实**，不是该运行当时发出的遥测计数。新增计数器仅用于未来事件；历史事件投影未添加任何合成计数字段。

**配套修正**：`online_evolution.py` 的 evolve 事件现在显式记录 `nsga3_parent_selection_calls` 与 `nsga3_survivor_selection_calls`（新增 3 项回归测试：恰好 4 已测量无溢出=0 调用、>4 已测量=1 调用、溢出=幸存者调用）。

## 5. 控制器使用整 episode 成本而非干预增量成本

`run_row` 在重试后把 `budget.ledger.known_cost_cny` 与 `provider_attempts`（含 attempt 1 的尝试）传给 `observe()`，候选适应度因此混入干预前成本，无法表达"干预的增量成本/调用"。R1.9 的历史观察保持原样，**不追溯改写**。

**更正（R1.10 起）**：`run_row` 在 attempt 1 后立即快照调用数与费用，attempt 2 结算后仅将**增量**传给控制器（CEA-v2.1 版本化契约，见 `docs/PHASE4_R1_10_ALGORITHM_FIDELITY.md`）。

## 6. no-op 表型未获得反馈

`genome_to_text()` 返回 None 时，`run_row` 提前返回且未调用 `observe()`，空/no-op 表型因而没有结果更新。

**更正（R1.10 起）**：no-op 选择显式记录最终失败与零增量成本/调用并恰好观察一次（不额外发模型请求），且基础设施/未知费用结局永不作为行为奖励。
