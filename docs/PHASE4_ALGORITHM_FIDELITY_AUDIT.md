# Phase 4 算法保真审计（P4-R1.1-S2）

日期：2026-10-14。审计对象：2026-10-14 pilot（run phase4-live-20261014T110259Z）的六臂真实调用路径。原则：旧行不改写，语义如实标注。

## 1. 逐臂真实调用路径（审计时代码：src/causalevo/eval/live_pilot.py）

| 臂 | 名义 | 真实执行语义 | 结论 |
|---|---|---|---|
| B0-original | 原始 agent | `run_task_arm` 单次 `runner.run_task`，无重试 | 属实 |
| B1-random | 随机干预 | `rng.choice(sorted(INTERVENTION_TEXT))` 选固定文本重试 | 属实（随机源已记录） |
| B2-rule | 规则干预 | if/else 观察证据 → 固定文本（invalid→verification；无编辑→planning；failure_kind≠none→tool_validation；否则 read_before_write） | 属实但为**固定启发式**，无独立 diagnosis 模块调用 |
| B3-reflexion | 反思重试 | 固定反思模板 + visible 失败名 | 属实 |
| B4-cea-v0 | LinUCB 选择 | **未调用** `CausalEvolutionController.select_intervention`；实际为 if/else 代理 | **名义与执行不符**（proxy） |
| B5-cea-v1 | NSGA-III 策略 | **固定** `CEAV1_BUNDLE = tool_validation + verification` 文本；未读 pareto_front.json、未按状态选择 | **名义与执行不符**（静态 bundle） |

A1–A4（报告中的消融）是离线构造/代理映射，不是独立 live 消融 —— 如实标注。

## 2. 修复：CausalPolicyAdapter（src/causalevo/evolution/adapter.py，adapter_version="r1.1"）

- **cea-v0 模式**：`CausalPolicyAdapter.cea_v0(policy_snapshot)` 载入冻结 LinUCB 快照；`select()` 真实调用 `CausalEvolutionController.select_intervention`；评估期 `updates` 不变（冻结部署）；policy_version 含状态哈希。
- **cea-v1 模式**：读取 `results/phase3/evolution/pareto_front.json`，校验基因组 id 与文件 SHA-256；`intervention_for()` 从基因组活动基因派生干预文本（非硬编码）；基础设施失败直接 escalate（不重试）。
- 离线行为由 tests/test_causal_policy_adapter.py 9 项证明；不混入旧 312 行。
- 旧臂重命名映射（文档级，不改历史文件）：B4→"B4-proxy-heuristic"，B5→"B5-Pareto-static-bundle"。

## 3. 边界声明

- 离线进化（NSGA-III）与 live 评估的边界：评估只部署冻结产物；训练任务与评估任务隔离；任何按测试集结果调参 = leakage（协议禁止）。
- 新 adapter 本轮只证明离线行为闭环；真实模型结果需新授权 pilot。
