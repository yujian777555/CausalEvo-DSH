# Phase 1.6 评测协议（冻结）

日期：2026-10-14。本文是论文级评测的顶层协议；B0/B1、指标、统计检验、停止规则在此冻结。与 `docs/PHASE1_EXPERIMENT_PROTOCOL.md`（运行时/指标模式）和 `docs/PHASE1_STATISTICAL_PLAN.md`（统计方法）一致；冲突时以最新 dated 章节为准并需 Planner 批准。

## 1. 任务体系（冻结）

| 层 | 内容 | 角色 |
|---|---|---|
| Engineering regression | `benchmarks/tasks/` 26 个 microtasks | 仅工程回归；`role=engineering_regression`、`paper_eval_eligible=false`；**永不作为论文 unseen test** |
| 外部基准 | SWE-bench Verified（revision `c104f840…`，见 PHASE1_6_BENCHMARK_FREEZE.md） | 论文主基准候选；实例选择标准已冻结 |
| Private holdout | `../CausalEvo-DSH-holdout`（Git 外，`benchmarks/holdout_manifest.json` 仅存哈希） | 论文最终未见集；当前 3 个样例任务 |

## 2. 基线（冻结，引用不重复）

- B0-fixed-harness、B1-self-reflection-fixed-budget，同预算包络（2 provider calls / 2048 output tokens / 20 tool calls / 300s）。定义与平价强制见 PHASE1_EXPERIMENT_PROTOCOL.md §1。
- 未来 CausalEvo 臂必须在同一包络、同一 profile、同一 judge 下比较。

## 3. Private holdout 机制（冻结）

- 存储：Git 仓库之外（默认 `../CausalEvo-DSH-holdout`，可用 `CE_DSH_HOLDOUT_DIR` 覆盖）；**内容永不进入 Git**，只有哈希清单入库。
- Agent 不可访问：agent 容器只挂载 workspace 拷贝；holdout 目录从不挂载（`tests/test_holdout.py` 守卫）。
- Judge 可访问：judge 侧按路径加载并核对哈希。
- 完整性：创建时哈希钉死；`verify_holdout()` 逐字节复核，篡改即失败。
- Split：固定 `split=holdout`，创建即冻结，不重新洗牌。
- 泄漏处理：一旦任何 holdout 内容进入 Git/日志/轨迹，该 holdout 作废并记录事件。

## 4. 指标（冻结）

沿用 PHASE1_EXPERIMENT_PROTOCOL.md §2 的三轴指标（任务轴 task_success/visible_pass/hidden_pass/timeout/invalid/budget_stop；agent 轴 provider_calls/tool_calls/tokens/cache_hit/cost/trajectory；安全轴 sandbox_violation/network_violation/permission_denied）。成功口径不变：visible AND sealed AND 非 invalid AND 非 timeout。

## 5. 统计检验（冻结）

沿用 PHASE1_STATISTICAL_PLAN.md：paired tasks + 预登记 seed（20261010/20261011/20261012，执行顺序 shuffle seed 20261013）；主比较 = B0 vs B1（及未来 vs CausalEvo）的 task_success，McNemar exact + Clopper-Pearson（b+c<25 强制）；per-arm Wilson 仅描述；成本/token 差值用 paired bootstrap（10k）。多重比较纪律与反钓鱼条款不变。

## 6. 停止规则（冻结）

1. 预算或安全门触发（unknown_spend、budget_stop、sandbox_violation ≠ 0）→ 立即停止该 run 并标记。
2. 数据质量门：invalid > 10% 或 timeout > 30% → 该批次仅作工程证据，不进对比。
3. 外部基准 pilot 前必须完成 oracle 对照 smoke（官方镜像 + gold patch 能 resolved），否则 pilot BLOCKED。
4. 不允许基于中途结果的提前停止或追加任务。

## 7. 本轮状态

- 工程平台：Phase 0–1.5 已冻结验收。
- 本协议自 2026-10-14 冻结；变更仅能以 dated 章节追加 + Planner 批准。
- 本轮零 live API 调用、零费用。
