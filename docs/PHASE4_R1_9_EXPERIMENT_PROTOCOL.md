# CE-DSH-P4-R1.9 — 正式实验协议（冻结，live 前锁定）

日期：2026-10-24。状态：**已冻结，执行前不得更改**。本协议取代 R1.7 草案的条件 GO 与 R1.8 的 NO-GO（后者为用户授权前的 Planner 保守决定）；**本轮用户已显式授权真实 API 调用，硬上限 ¥2.00**。

## 1. 估计目标与主要终点（冻结，未看任何新结果前确定）

- **主要终点**：每个 (task, seed, arm) 行的 **final_success**（二值，固定分母 = 全部预定行）。
- **主要比较**：CEA-v2-online vs B1-random 的配对成功率差。
- **次要比较**（Holm 校正）：CEA-v2 vs B5-v1-frozen-pareto；CEA-v2 vs B0-original；B5-v1 vs B1-random。
- **次要描述性指标**：首轮成功率；首轮失败后恢复率（分母 = attempt1 失败且发生重试的行，明确列出，不与主检验混用）；调用次数、token、费用、延迟；在线更新次数；有效表型多样性与谱系。

## 2. 统计检验与决策规则（冻结）

- 主检验：**配对 McNemar 精确检验**（所有配对行的 final_success）。
- 区间：**任务级聚类 bootstrap**（10,000 次重采样，95% CI；同 task 的 2 种子聚类）用于配对成功率差。
- 多重比较：主比较 1 个；次要比较按 Holm。
- 判定规则（预先声明）：
  - "有提升证据" 当且仅当：McNemar 校正后 p < 0.05 **且** 配对差 CI 下界 > 0。
  - 最小实际相关效应参考值：+0.10（用于解释，不作为 H0 的补充假设）。
  - CI 跨 0 或 p 不显著 → **无提升证据**（如实报告，不修饰）。
- **功效/敏感性**：26 任务簇 / 52 任务-种子对。若不一致对很少（如 < 8），只能探测大效应；此时**明确标注探索性 pilot**，不承诺确认性结论。
- 26 个公开 microtasks 为工程/pilot 任务，**不是**论文 unseen test 数据。

## 3. 冻结任务与种子

- 任务：`benchmarks/tasks/` 26 个 microtask（130 个文件），**canonical manifest SHA-256 = `fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`**（排序相对路径→文件 SHA-256 的 JSON 的 SHA-256）。
- 种子：`[20261014, 20261015]`。
- 臂执行顺序：每个 seed 内按任务清单顺序，每任务依次 B0-original → B1-random → B5-v1-frozen-pareto → CEA-v2-online（CEA-v2 的状态按行序推进；其他臂无状态）。

## 4. 臂与真实代码路径（冻结）

| 臂 | 代码路径 |
|---|---|
| B0-original | `run_phase4_r19_pilot.py::run_row`（单次尝试，不重试） |
| B1-random | 同函数，`rng.choice(sorted(INTERVENTION_TEXT))`（冻结随机源） |
| B5-v1-frozen-pareto | `CausalPolicyAdapter.cea_v1_from_manifest` + `select_genome` + `intervention_for`（全程零更新） |
| CEA-v2-online | `OnlineEvolutionController`（`online_evolution.py`）：失败→select（当前统计+探索）→重试→独立 Judge + 账本结算→observe→（每 4 条行为观察）NSGA-III 演化步骤 |

配置：`model=deepseek-flash`、`reasoning_effort=low`、`max_tokens=256`。控制器配置：`update_every=4`、`max_population=16`、`mutation_p=0.25`、`n_offspring=4`、`exploration_beta=0.05`、`lambda_cost=50.0`、`lambda_calls=0.02`、`seed=20261021`（config SHA-256 随 manifest 记录）。

## 5. 预算与上限（冻结）

- **全局硬上限：¥2.00**（ProxyContainer `cap_cny=2.00`，逐请求原子预留 + 结算）。
- 内部预警线：¥1.80（达到即停，为结算误差/在途预留余量）。
- **每 scope（run/task/seed/arm）请求上限 = 8**（与 `RuntimeBudget(max_provider_calls=8, max_total_output_tokens=2048, max_tool_calls=20, wall_time_s=240)` 一致）。**依据（canary 实测）**：真实 DSH agent 每次 attempt 使用 3 次 provider 请求（read/write/text），历史 312 行的 `provider_calls` 分布为 2–8（2:50, 3:197, 4:57, 5:4, 6:3, 8:1）。初版 cap=2 被 canary 证伪：第 3 次请求被 proxy 拒绝并产生 `unknown_cost`，已修正为 8（每 attempt ≤4 请求 × 2 attempts 的包络）。
- 每任务行预算：8 provider 请求、2048 输出 token、20 工具调用、240s 墙钟。
- 计价口径注意：proxy 预留/结算按 **peak** 费率（保守上限），行级账本按 **off_peak** 报告（`harness_agent.py` 既有口径）；硬上限以 peak 结算为准，保证任何时段都不超 ¥2.00。
- 缓存计费口径：`pricing.py` 已披露规则（cache_read 命中价、cache_write 按未命中价上限）；不得因缓存命中假定免费。
- 账本独立：本轮 run_dir 下 `proxy-ledger/ledger.jsonl`，不复用历史账本、不换 run_id 重置费用。

## 6. 停止规则（fail-closed，冻结）

- 任一请求 `unknown_cost` / 账本损坏 / 在途费用不确定 / 5xx / 断流 / 协议错误 → 全局停止，保存账本与已完成行，不后续重试。
- `unknown_cost`、`budget_stop`、`transport`、`protocol` 结局：**不产生行为学习更新、不做行为重试**（基础设施结局单列）。
- 达预警线或硬上限 → 按已完成行分析并标注截断；不得为凑样本突破上限。

## 7. 记录与可复现性（冻结）

- 每行立即写 `tasks.jsonl`：episode_id、task_id、seed、arm、attempt 状态、final_success、intervention_text、selected_genome_id、policy_version、population_version、selection_reason、controller_update、provider_calls、input/cache/output tokens、cost_cny、latency_ms、abort_reason。
- 控制器事件逐条追加 `events.jsonl`（含 evolve 事件与谱系）；`controller_state.json`；`manifest.json`（任务清单哈希、配置哈希、种子、cap、provenance）。
- 分析脚本 `scripts/analyze_r19_pilot.py` 从行记录重算全部指标（可独立复算）。
- 历史 312 行不可修改、不与本轮行合并进同一确认性分析。

## 8. 运行前检查（全部通过方可 live）

1. 远端 SHA/工作区/冻结哈希核对；2. 密钥仅经受控环境进入 Proxy（裸 -e 透传，agent 仅持 per-run token）；3. BudgetProxy + 独立 Judge 就绪；4. 入口模型 `deepseek-flash`；5. fake-provider 全路径通过（CEA-v2 闭环）；6. 直连配置复核（TUN 关闭、无 deepseek 代理规则变更）；7. 账本闭环（canary 验证计量）；8. 控制器收到已结算反馈且后续选择确实改变。

**canary（1 任务 1 臂，计入预算）通过后才进入完整 pilot。**
