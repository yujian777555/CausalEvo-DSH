# CE-DSH-P4-R1.7 — 预注册实验提案（Preregistration，仅方案，不执行）

日期：2026-10-21。状态：**提案，不是授权**。任何未来 pilot 需要用户显式预算授权 + GPT Planner 批准。本轮 0 次真实 API 调用、¥0。

依据：docs/PHASE4_R1_7_ALGORITHM_FIDELITY.md（算法真实性审计）。

## GO / NO-GO 判定：**有条件 GO（限小规模预注册 pilot）**

理由：

- 历史 312 行**没有**测试真实算法臂：B4 实为 if/else 代理、B5 实为静态 bundle（审计 C6）。真实适配器臂（B4-v2 = 冻结 LinUCB 快照；B5-v2 = 冻结 Pareto 前沿的失败条件化选择）**从未经过 live 测试**。
- 因此存在一个新的、可证伪的、公平的比较：真实冻结算法臂 vs 随机干预基线（历史上最强的基线）。这不是重复已知的负面对比——历史 run 测试的是不同（代理）实现。
- 诚实边界：该 pilot 验证的是**冻结演化策略的部署效果**（L1 运行时 + 离线 L3 产物），**不是**递归自我改进（L4 未实现，审计 C4）；即使结果为正面，也不能宣称 Agent 已"自进化"。
- 若该 pilot 中 B5-v2 不能显著超过 B1-random，则冻结策略路线在真实模型上失败，后续应先做运行时在线更新（L2）再谈 L3/L4。

## 1. 主要假设（可证伪）

H1：在相同任务/种子/预算下，**B5-v2 的失败后恢复率（recovery rate）高于 B1-random**，配对差值的效应量 ≥ 0.10（10 个百分点）。
原假设 H0：恢复率差 ≤ 0。

次要假设 H2：B5-v2 的总成本不高于 B1-random 的 1.2×。

## 2. 主要终点与效应阈值

- 主要终点：**recovery rate** = attempt-1 失败后 attempt-2 成功的比例（每行：同一 task+seed，两臂配对）。
- 效应阈值：+0.10（配对比例差）。次要终点：final pass rate、总费用、总 token。

## 3. 固定任务划分与种子

- 任务：benchmarks/tasks/ 现有 26 个 microtask（task_registry 哈希固定；manifest 记录 `benchmarks/tasks` 目录内容 SHA-256）。
- 种子：SEEDS = [20261014, 20261015]（与历史一致，固定）。
- 配对：同一 (task, seed) 下各臂共用相同 workspace 初始状态与失败 tape 结构（live 时由模型真实执行，配对靠同 task+seed 的 paired 分析）。
- 不使用 private holdout（本轮不涉及；任何确认性结论须另案）。

## 4. 实验臂与实际代码路径（冻结）

| 臂 | 代码路径 |
|---|---|
| B0-original | `run_task_arm` 单次尝试，不重试 |
| B1-random | `rng.choice(sorted(INTERVENTION_TEXT))`（历史真实路径，不动） |
| B4-v2 | `CausalPolicyAdapter.cea_v0(frozen LinUCB snapshot)` → `select()`（冻结，不更新）；动作→文本映射 ACTION_TO_TEXT（预注册冻结） |
| B5-v2 | `CausalPolicyAdapter.cea_v1_from_manifest(pareto_front.json, configs/phase3_artifact_manifest.json)` → `select_genome(failure_kind, edited, invalid)` → `intervention_for`（冻结规则；基因组→文本派生） |

所有臂共用：BudgetProxy（逐请求门控、scope=run/task/seed/arm、unknown_cost fail-closed）、RuntimeBudget、独立 Judge、ContainerHarnessRunner（agent 仅持 proxy token）。

## 5. 预算与上限（基于实测）

实测依据：历史 312 行总费用 ¥0.715（status.json phase4.spent_cny），平均每行 ≈ ¥0.0023。

| 档 | 行数估算 | 费用估算 | 说明 |
|---|---|---|---|
| 低 | 26×2×4=208 行 × 1.2 请求/行 | ≈ ¥0.35 | 假设缓存命中与历史相当（实测口径） |
| 基准 | 208 行 × 1.5 请求/行 | ≈ ¥0.50 | 含约 50% 重试率（历史观测区间） |
| 高 | 208 行 × 2 请求/行 + 峰值计价 | ≈ ¥1.00 | 全部为未命中缓存+峰值价（保守上限） |

- **硬上限：¥2.00**（Proxy 全局 cap；达到即停）。
- 每 scope 请求上限：8（=2 次 attempt × 每 attempt 最多 4 次 provider 请求的上界）。
- 缓存计费口径：cache_read 按命中价、cache_write 按未命中价上限（沿用 pricing.py 已披露规则）。

## 6. 统计方案

- 主检验：**McNemar 精确检验**（B5-v2 vs B1-random 的恢复结局，配对）。
- 置信区间：task-level cluster bootstrap（10,000 次重采样，95% CI；同 task 两种子聚类）。
- 效应量：配对比例差 + Cohen's h。
- 多重比较：主比较仅 1 个（B5-v2 vs B1）；次要比较（B4-v2 vs B1、B5-v2 vs B0）按 Holm 校正。
- 禁止：根据结果更换主终点/主比较；任何探索性分析必须标注 exploratory。

## 7. 停止规则（fail-closed，与现有代理一致）

- 任一请求 unknown_cost / 5xx / 断流 / 预算预留超限 → 全局停止，保留账本，记录已发送请求数与已知费用。
- 预算达 ¥2.00 → 停止，已完成行照常分析（在报告中标注截断）。
- 协议偏差（如模型返回非预期 schema）→ 该行标记 invalid，不补跑，如实计入。

## 8. 可复现性与输出

- 结果写入新目录 `results/phase4/live2-pilot-<run_id>/`（**不覆盖** 2026-10-14 目录）；manifest 含：git SHA、镜像 digest、artifact manifest 哈希、种子、臂、cap、环境探针（代理/TUN 状态重检）。
- 每行记录：task_id/seed/arm/attempt 状态/provider 请求数/token/费用/轨迹哈希。
- 完成后重新生成 auditable 投影并独立复算（reconcile 脚本）。

## 9. 历史数据隔离

- 2026-10-14 的 312 行为**探索性/历史数据**，永不修改；**不与**新 pilot 行合并进同一确认性分析；如需参考，只能作为独立的先验信息标注。

## 10. 执行前置条件（全部满足才可申请预算）

1. 本提案经 GPT Planner 批准 + 用户显式预算授权（≤¥2.00）。
2. 直连诊断在当前配置下重新确认（TUN 状态未变）。
3. BudgetProxy/适配器在当前 HEAD 通过全部离线测试 + clean-clone Gate。
4. 预注册的臂、终点、阈值、统计方案写入 `preregistration.json` 并提交后再开始任何 live 调用。

**再次声明：本文件是提案，不是授权；本轮不执行任何真实 API 调用。**
