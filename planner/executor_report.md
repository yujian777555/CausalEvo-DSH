# Executor Report — CE-DSH-P4-R1.11（敏感性可复现与状态收尾）

日期：2026-10-26。Executor：Kimi。**本轮 0 次真实 DeepSeek 调用、¥0 新增费用；未查询余额。**

计划：planner/latest_plan.md（CE-DSH-P4-R1.11）；审查：planner/reviews/CE-DSH-P4-R1_10-independent-review.md。

## A. Git 状态

- 起始 SHA：`ef7348bfff2d53328b867ddb134356147db9baf9`（与预期 Planner 提交一致，工作区 clean）
- 最终 SHA / 远端 SHA / clean-clone 验证 SHA：见末节「Git 交付」

## B. Task A：精确簇级敏感性可复现（完成）

- 新增 `scripts/analyze_r19_cluster_sensitivity.py`：对 26 个任务簇的配对均值差（**两种子始终同簇**）做**精确动态规划符号翻转**，枚举全部 2^26 符号分配，输出精确双侧 p，无 Monte Carlo 噪声。
- 从 `results/phase4/r19-audit/auditable_tasks.jsonl`（208 行）重算，精确结果：

| 比较 | 精确双侧 p |
|---|---|
| CEA-v2 vs B1-random | **0.750000** |
| CEA-v2 vs B5-v1-frozen-pareto | **0.625000** |
| CEA-v2 vs B0-original | **0.7265625** |
| B5-v1-frozen-pareto vs B1-random | 1.000000 |

- 与 Planner 独立精确枚举一致；此前 20000 次置换估计（0.7462/0.62095/0.7268）保留在 `previous_monte_carlo_estimates`，未覆盖或重标。
- `results/phase4/r19-audit/sensitivity.json` 已重生成，含 `label=POST_HOC_CLUSTER_AWARE_SENSITIVITY`、`not_preregistered_primary=true`。**预注册 McNemar/成功率/费用/探索性结论均未改动。**
- 测试 `tests/test_cluster_sensitivity.py` **8/8**：26 簇与双种子保持、精确 p 值、双侧尾部/并列处理、缺臂/重复键/缺种子拒绝、事后标签、两次重生成字节一致。
- `manifest_reconciled.json` 新增 `sensitivity_artifacts`：`script_sha256` 与 `output_sha256`（无自指哈希）。

## C. Task B：账本数据边界（完成，无伪造字段）

- 源 proxy 账本**不含逐请求 token 桶与定价档位**。明确写入 `manifest_reconciled.json.field_definitions.token_limitations` 与 `docs/PHASE4_R1_9_RECONCILIATION.md`：
  - 可独立复算：SETTLED 成本求和 + UNKNOWN 预留上界（1.3063390536 + 0.15704064 = 1.4633796936）。
  - 行级聚合 token 桶存在于 `auditable_tasks.jsonl`（input/cache_read/output），但不能映射回每个 proxy 请求。
  - **逐请求 token 级重计价不可独立复现**，不伪造这些字段。
- `auditable_ledger.jsonl` 新增 `seq`（保留各 run 内源文件顺序，共 2755 条迁移），其余字段（request_id/scope/状态/预留/结算/安全备注）完整保留。
- `intervention_text` 有意保留（动作级审计）；口径改为：排除原始请求/响应体、完整 provider payload、凭据与原始会话日志，而非笼统"无 prompt"。

## D. Task C：status.json 元数据归一（完成）

- 当前顶层 `planner_review`（R1.10 审查）、`review_path`（R1_10 独立审查）、`phase`、`phase_status=READY_FOR_REVIEW`、`next_actor=GPT-Planner`、`next_goal`、`baseline_main_sha` 与当前 HEAD 字段已按本轮实际更新；历史 R1.7/R1.9 审查记录保留于历史键。
- `tests.categories.online_evolution_controller = 19/19`（与 Executor 输出一致）。
- `clean_clone_tested_sha = 5d5777c80713356e2c0e2049e94e8499f8dc16dd`（已测）与当前 docs-only HEAD `2bb9e5c3e6f9ac8c01e9f2529d4939459b055b1e`（当时未测）明确区分；本轮新的最终 SHA 将在末节记录。
- 删除"投影缺失/费用不可验证"等过时结论；保留历史说明并标注为 pre-R1.10。
- `limitations` 更新为当前事实：GPT 未独立重跑、CEA-v2 无优越性证据、L4 RSI 未实现、逐请求重计价不可得、敏感性脚本已可复现。
- JSON 解析通过、键唯一。

## E. Task D：NSGA-III 遥测口径（完成）

`docs/PHASE4_R1_9_CORRECTION_ADDENDUM.md` 与 `docs/PHASE4_R1_10_ALGORITHM_FIDELITY.md` 已明确：
- 历史 evolve 事件**不含**新加入的调用计数字段（计数器在实验后加入）；
- "0 次调用"是**依据归档源码分支条件与归档控制器状态重建的事实**，不是当时输出的遥测；
- 新计数器仅用于未来事件，历史投影未添加合成计数。

## F. 验证矩阵（实际命令与真实输出）

| 项 | 命令 | 结果 |
|---|---|---|
| 敏感性脚本×2 | `python scripts/analyze_r19_cluster_sensitivity.py`（两次） | 输出字节一致 |
| 敏感性测试 | `pytest tests/test_cluster_sensitivity.py -q` | 8 passed |
| 控制器 | `pytest tests/test_online_evolution.py -q` | 19 passed |
| 增量适应度 | `pytest tests/test_incremental_fitness.py -q` | 4 passed |
| 分析 | `pytest tests/test_analyze_r19.py -q` | 4 passed |
| 预算四套件 | `pytest tests/test_budget_proxy{,_r14,_r15,_r16}.py -q` | 102 passed |
| 凭证/控制/e2e/适配器/v2 | 五文件联合 | 50 passed |
| **全量** | `pytest tests/ -q` | **631 passed / 0 failed / 0 skipped** |
| clean-clone（精确最终 SHA） | `python scripts/clean_clone_check.py` | 见末节 |

无 NOT_VERIFIED 项；Docker 全程可用。

## G. 费用与安全

- 本轮真实模型调用 **0 次**、费用 **¥0**；未查询余额。
- 冻结哈希：`calls.csv` `1961bdd8…`、`auditable_tasks.jsonl` `35b9e67a…`、sweep `15e2cb84…` 未变；Phase 0–3 与历史 312 行零改动。
- 密钥扫描：`git diff --cached | grep -cE "sk-[A-Za-z0-9]{32}"` = 0。

## H. 未解决问题

1. R1.9 的 CEA-v2 无提升证据（探索性）；本轮仅完成分析与可复现性收尾，不产生新的模型性能结论。
2. 逐请求 token 级重计价不可得（源账本字段缺失，已明确披露）。
3. L4 递归自我改进未实现；后续确认性实验需簇感知主检验与新的用户预算授权。
4. Planner 未独立重跑本机测试；全部数字为 Executor 实际终端输出。

## I. Git 交付（精确最终 SHA / clean-clone / 同步）

- **R1.11 主提交：`3ecd7691e8d93d8357b60531e1722b1d5ba4e044`**（push 后 `git ls-remote origin main` 与本地 HEAD 一致）。
- **最终 SHA Gate（逐字输出）**：
  ```
  verified: 312 auditable rows recompute to the committed analysis (incl. cluster bootstrap)
  34 passed in 4.48s (phase4 subset)
  208 passed in 369.64s (key suites incl. test_cluster_sensitivity exact DP)
  CLEAN CLONE OK: HEAD 3ecd7691e8d9 == origin/main; 312 auditable rows recompute in a fresh clone
  exit=0
  ```
- **clean-clone 验证 SHA（完整）**：`3ecd7691e8d93d8357b60531e1722b1d5ba4e044`（脚本强制 clone HEAD == ls-remote，失配 exit 2；命令行显式传入该 SHA）。
- 本记录提交（housekeeping）仅改 status.json 与 executor_report.md，不含代码/测试变更；按惯例如实声明：Gate 在 `3ecd769…` 通过，记录提交本身未再触发 Gate（如需可用 `python scripts/clean_clone_check.py <sha>` 随时对当前 HEAD 重验）。
- 同步状态：本地 HEAD == `git ls-remote origin main`；`git status --porcelain` = 0（clean）。
- 冻结校验：staged diff 中 results/phase0–3 与 results/phase4/live 零改动；密钥扫描 0 命中。

## 停止

停在 Phase 4 R1.11。未进入付费 pilot 或 Phase 5。`next_actor = GPT-Planner`。
