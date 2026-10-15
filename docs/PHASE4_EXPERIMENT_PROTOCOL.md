# Phase 4 实验协议（冻结，先于任何 live 调用）

日期：2026-10-14。本协议在任何 live 实验前冻结；指标在看到结果后不得修改（修订需 dated 章节 + Planner 批准）。

## 修订 2026-10-15（口径澄清，非指标变更）

§2 中"每任务 ≤2 次 provider 调用（首次 + 一次干预重试）"的"provider 调用"指 **agent attempt**（一次 runtime run）。attempt 内工具循环会产生多次 LLM 请求（实测每任务 2–8 次），由 RuntimeBudget 逐条记账。此澄清不改变任何指标、预算或结果。

## 1. Benchmark 与任务（冻结）

- Pilot 任务集：26 个本地 microtasks（engineering regression；非论文 unseen benchmark）。
- 定位：验证"CEA 生成的策略在真实 Agent 上是否提高成功率"的最小可控实验；外部 SWE-bench pilot 需另行授权。
- 种子：[20261014, 20261015]（每任务每臂各种子一次）。
- 判分：独立 judge（Docker），visible AND sealed 全过且非 invalid/timeout 才算成功；与冻结协议一致。

## 2. Baselines（冻结）

| 臂 | 定义 |
|---|---|
| B0 Original | 单次尝试，无干预 |
| B1 Random | 失败后随机选一个干预指令重试一次（seed 固定） |
| B2 Rule | 失败后按 taxonomy 规则映射干预 |
| B3 Reflexion | 失败后把 visible 失败信息回灌，结构化反思一次 |
| B4 CEA-v0 | 失败后由 LinUCB（Phase 3.1 训练）选择干预 |
| B5 CEA-v1 | 失败后施加 Phase 3.2 Pareto 前沿选定基因组策略（tool_validation + verification） |

所有臂共享同一任务预算包络：每任务 ≤2 次 provider 调用（首次 + 一次干预重试）、max_tokens=256/请求、wall 240s、judge 不计入。

## 3. 干预指令库（live 版，冻结）

| 干预 | 注入文本（重试时追加的 user 消息） |
|---|---|
| tool_validation | "Use ONLY these tools with valid arguments: read, write, edit, glob, grep. Read the target file before writing." |
| verification | "Before finishing: re-read every file you wrote and check it parses/imports; if not, fix and re-check." |
| reflection(B3) | "Your previous attempt failed these visible checks: <names>. Briefly diagnose why, then apply the corrected fix." |
| read_before_write | "First read solution.py, then write the fix." |

## 4. 指标（冻结）

- Success：pass rate、solved tasks（每臂×种子）。
- Efficiency：total tokens、API cost（CNY，价格页 2026-10-10 费率 + 逐次记录 tier）、execution steps、latency。
- Adaptation：Recovery Rate = 首次失败后经干预成功的比例（分母 = 首次失败且触发重试的任务）。
- Evolution Gain：Success_CEA(v1) − Success_B0（及对各臂），配对统计：McNemar exact + paired bootstrap 95% CI。
- 因果对照：B5 vs B1（随机干预）是关键对照（RQ3）。
- Ablation：A1 无因果奖励（B4 用普通 outcome 训练的对照说明）、A2 无 NSGA-III（B4 vs B5）、A3 无诊断（B2 盲规则 vs B4/B5）、A4 无演化记忆（B4 不更新）。

## 5. 预算与停止规则（冻结）

- 授权：用户批准 Phase 4 live pilot；平台余额实测 ¥3.77（2026-10-14）。
- 本轮预算上限：**¥3.00**（余额内，留余量）；逐任务 RuntimeBudget + 全局 BudgetGate（peak 价最坏预留）；任何 unknown_cost/超限 → 全局 fail-closed 停止。
- 密钥只经 stdin 注入容器，不落盘；轨迹只存脱敏结构。
- 所有调用记录 results/phase4/live/；无记录调用视为违规。

## 6. 干跑要求

live 前必须完成同矩阵 fake-provider dry-run（零成本），证明调度/记账/judge 链路正确。
