# CE-DSH-P4-R1.7 — 算法真实性审计（Algorithm Fidelity Audit）

日期：2026-10-21。审计者：Kimi（Executor）。方法：**逐行阅读实际源码与工件**（非 README/汇报）；每条结论附文件、函数、测试或结果文件证据。本审计零 API 调用、¥0。

审计对象（全部实际读取）：`src/causalevo/evolution/{nsga3,genome,fitness,population,policy,controller,bandit,reward,memory,adapter}.py`、`scripts/run_evolution.py`、`scripts/run_phase4_v2_offline.py`、`results/phase3/evolution/*`、`results/phase3/replay_sweep/sweep_results.jsonl`、`configs/phase3_artifact_manifest.json`、历史 312 行（`results/phase4/live/phase4-live-20261014T110259Z/`）、`docs/PHASE4_ALGORITHM_FIDELITY_AUDIT.md`。

## C1. 离线进化是否真实执行？——**IMPLEMENTED_AND_TESTED（离线、tape 模拟干预、小规模）**

真实执行。证据：

- 驱动：`scripts/run_evolution.py::nsga3_evolve`（main 实际调用）——`Population.initialize`（6 个 rule seed + 随机补齐，去重，`population.py:50-69`）→ 逐代：`nsga3_select`（`nsga3.py:112-132`：fast_non_dominated_sort（真实支配排序，`:20-48`）→ Das-Dennis 参考方向（`:51-61`）→ ASF 归一化（`:64-79`）→ 垂直距离关联（`:82-91`）→ 小生境计数选择（`:135-147`））→ 均匀交叉 + 逐基因变异（`genome.py:60-72`）→ 子代带 parent_ids 谱系（`population.py` Individual）。
- 适应度：来自**真实反事实重放测量**——`run_evolution.py::evaluate_genome` 对每个 genome 依次应用 `genome.phenotype_transforms()` 生成 cf tape，经 `counterfactual.replay.run_single` 在容器世界真实执行（Docker agent + tape provider + Judge），记录 success_delta/cost_delta/extra_calls/cf_success；`fitness.fitness_from_measurements` 聚合 4 目标。**不是模型预测分数**。
- 多目标真实参与选择：`nsga3_select(fit, pop_size, rng)` 用全部 4 维目标做支配排序与小生境（非仅记录）。
- 参数与诚实标注：`results/phase3/evolution/evolution_manifest.json`（seed=20261014, pop=6, generations=3, mutation_p=0.25, train=[bad_tool_blocks_write, broken_write], test=[wrong_fix]，"replay-measured fitness; simulated interventions; zero API spend"）。
- 测试证据：`tests/test_nsga3.py`（排序/参考方向/归一化/关联/小生境/超体积）、`tests/test_evolution_e2e.py`（端到端工件、前沿非支配性、test_fitness 存在）、`tests/test_population_fitness.py`、`tests/test_genome.py`——全量套件中通过。
- **规模与性质限制（如实）**：pop 6 × 3 代 × 2 训练案例 × 2 任务；干预是 **tape 变换模拟**（非真实模型行为）；基因型 144 → 表型 16（R1.1 基因组审计）；`reflection_step`、`retry_strategy` 为 reserved 基因（无表型效果，`genome.py:21-22` 注释）。

## C2. Pareto 工件如何产生？——**IMPLEMENTED_AND_TESTED**

- 产生：`run_evolution.py::main` —— `pareto_front()` 取最终种群支配排序第 0 层（`run_evolution.py:146-148`），对每个前沿成员额外在**留出案例** wrong_fix 上评估 `test_fitness`，写 `results/phase3/evolution/pareto_front.json`（genome + train_fitness + test_fitness）。
- 版本化/校验：`configs/phase3_artifact_manifest.json`（manifest_version r1.3.1）钉住 canonical（LF 规范化）SHA-256：`41119e59…`（pareto_front.json）、`564f7d18…`（sweep_results.jsonl）；`adapter.py::cea_v1` **加载前**比对，缺失/不符即 ValueError；`_front_members` 每次读取复检。R1.4 已修复 EOL 敏感钉定并补公开 sweep 工件。
- 工件确实源于演化运行：`population_history.jsonl`（逐代个体+谱系）、`fitness_cache.jsonl`、`baseline_comparison.json`（B0/B1/B2/B3 同评估预算对照）、`ablation_results.json`（A1 无变异/A2 单目标/A3 无因果 reward/A4）。
- **发现的工件级瑕疵（如实记录）**：冻结前沿 6 个成员只有 **4 个唯一基因组**（一个基因组出现 3 次——最终种群交叉/变异后产生的重复个体进入前沿）；一个成员含 reserved 基因（reflection_step=1, retry_strategy=2），其表型实际仅为 tool_validation+verification。不影响"工件可验证"，但提示选择空间狭窄。
- 测试证据：`tests/test_causal_policy_adapter.py` 19/19（manifest 钉住、篡改拒绝、每次读取复检等）。

## C3. 运行时实际执行什么？——**STATIC_ARTIFACT_ONLY（运行时冻结部署；无运行时演化）**

- 运行时**不重新演化**。`CausalPolicyAdapter.cea_v1`（`adapter.py`）加载冻结前沿；`select_genome(failure_kind, edited, invalid)` 用**冻结规则**按可观察失败证据选前沿成员；`intervention_for` 从基因组活动基因派生干预文本。基础设施失败（unknown_cost 等）→ 不重试。
- 失败反馈运行时只改变"选哪个前沿成员/哪段干预文本"；**不更新** genome、适应度、种群或 Pareto 前沿；无完整运行时演化更新闭环（离线 `nsga3_evolve` 闭环只在 `scripts/run_evolution.py` 内）。
- cea-v0：冻结 LinUCB 快照，`select()` 真实调用 `CausalEvolutionController.select_intervention`，评估期零更新（`deployment="frozen-no-update"`，测试断言）。
- v2 离线驱动（`scripts/run_phase4_v2_offline.py`）：agent attempt-1（失败 tape）→ adapter 选择 → attempt-2（修复 tape + 选中干预文本）→ 独立 Judge；4 场景 × 2 臂；`evidence_class=adapter_integration_smoke`。
- 测试证据：`tests/test_phase4_v2_offline.py` 7/7（真实容器驱动各分支）；`tests/test_causal_policy_adapter.py`。

## C4. 是否实现递归自我改进（RSI）？——**NOT_IMPLEMENTED（第 4 级）**

分层判定：

| 层级 | 状态 | 证据 |
|---|---|---|
| L1 Agent 根据反馈修复当前任务 | IMPLEMENTED_AND_TESTED | `live_pilot.run_task_arm` 失败后重试；v2 驱动 attempt-2（tests/test_phase4_pilot.py、test_phase4_v2_offline.py） |
| L2 根据反馈调整策略选择/概率 | IMPLEMENTED_AND_TESTED（**仅离线模拟**；运行时冻结不更新） | Phase 3.1 LinUCB 训练循环（`evolution/policy.py`、`controller.py`、`bandit.py`、`reward.py`；`tests/test_evolution_bandit.py`、`test_evolution_controller.py`、`test_cea_simulation.py`）；部署侧 `adapter.py` frozen-no-update |
| L3 演化搜索产生更优策略 | IMPLEMENTED_AND_TESTED（**仅离线**、tape 模拟、小规模） | `nsga3.py` + `run_evolution.py` + 工件（见 C1/C2） |
| L4 子代改进器改善后续子代的生成/评价机制 | **NOT_IMPLEMENTED** | 无元演化、无算子自适应更新、无自我修改代码路径；`genome.py`/`nsga3.py` 中 mutation_p、交叉规则、适应度定义在运行中恒定 |

**当前系统 = 静态失败条件化干预选择（L1 运行时 + 离线 L2/L3 产物）**，不是递归自我改进。

## C5. 现有证据到底支持什么？

| 性质 | 分类 | 证据 |
|---|---|---|
| 离线 NSGA-III 真实执行（排序/参考方向/小生境/超体积） | IMPLEMENTED_AND_TESTED | C1 所列测试 |
| 适应度来自重放测量（非模型预测） | IMPLEMENTED_AND_TESTED | run_evolution.py::evaluate_genome + fitness.py + e2e 测试 |
| Pareto 工件产生/版本化/钉住 | IMPLEMENTED_AND_TESTED | C2；test_causal_policy_adapter.py |
| 运行时失败条件化策略选择 | IMPLEMENTED_AND_TESTED（fake provider） | test_phase4_v2_offline.py |
| 运行时演化/策略更新闭环 | **NOT_IMPLEMENTED**（冻结部署为有意设计：防测试集泄漏） | adapter.py |
| L4 递归自我改进 | **NOT_IMPLEMENTED** | C4 |
| 真实模型上的算法提升 | **NOT_IMPLEMENTED / 无证据** | 见下节历史结果 |

## C6. 基线保真（历史语义不得追溯改写）

- 历史 312 行（2026-10-14 pilot）：**B4 实为 if/else 代理启发式**、**B5 实为固定 tool_validation+verification 静态 bundle**（docs/PHASE4_ALGORITHM_FIDELITY_AUDIT.md 已标注"名义与执行不符"；文档级改名 B4-proxy-heuristic / B5-Pareto-static-bundle，历史文件未改）。
- 后续 R1.1–R1.5 的 CausalPolicyAdapter（真实 LinUCB / 真实冻结前沿）只经 fake-provider 离线 smoke 验证（run-20261020T104048Z），**不与历史 312 行混合、不回填**。

## C7. 科学证据现状（如实复述）

- 历史配对实验（26 任务 × 2 种子 × 6 臂，¥0.715）：B0 0.808 / B1-random 0.923 / B2 0.885 / B3 0.827 / B4 0.846 / B5 0.885。
- B5 vs B0：+0.077，McNemar p=0.344（不显著）；**B5 vs B1（随机干预）：p=0.727，随机基线反而最高**；cluster bootstrap CI 跨 0。
- 结论保持：**平台端到端可信，算法优越性未获证据**；NSGA-III/LinUCB 在真实模型上的效果**没有任何 live 证据**（仅有 fake-provider 离线 smoke）。

## 对下一轮的含义

在此代码状态下，新 live pilot 若仍比较"B0 vs 静态 bundle/启发式"，只会重复已知的非显著比较。**有意义的实验**必须先实现真实运行时演化更新（至少 L2 运行时在线更新 + 冻结预注册规则），见 docs/PHASE4_R1_7_PILOT_PROPOSAL.md。
