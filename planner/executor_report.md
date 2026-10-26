# Executor Report — CE-DSH-P4-R1.10（证据对账与算法保真修复）

日期：2026-10-26。Executor：Kimi。**本轮 0 次真实 DeepSeek 调用、¥0 新增费用。** 未运行 `--live`、未查询余额。

计划：planner/latest_plan.md（CE-DSH-P4-R1.10）；审查：planner/reviews/CE-DSH-P4-R1_9-independent-review.md。

## A. Git 状态

- 起始 SHA：`f74c8a3e79679f305c3600b899ee9f2336c5a815`（与预期一致，工作区 clean）
- 最终 SHA / 远端 SHA / clean-clone 验证 SHA：见末节「Git 交付」

## B. Task A：恢复并提交脱敏证据（完成）

原始 `tasks.jsonl`、`events.jsonl`、`proxy-ledger/ledger.jsonl` 均在本机存在，**未标记不可复现**。已生成并提交：

- `results/phase4/r19-audit/auditable_tasks.jsonl`（208 行，逐 `(task,seed,arm)` 唯一键）
- `results/phase4/r19-audit/auditable_events.jsonl`（控制器行为/infra/evolve 事件，带 seq 与谱系）
- `results/phase4/r19-audit/auditable_ledger.jsonl`（全部 R1.9 run 的请求状态迁移，含 request_id/scope/状态/预留/结算/备注，**不含**请求体、prompt、密钥、Authorization 或原始会话日志）
- `results/phase4/r19-audit/manifest_reconciled.json`（源文件与投影哈希、每 run 与全轮费用、终态计数、UNKNOWN 上界、字段定义）
- `.gitignore` 仅对这 3 个脱敏投影加窄白名单。

## C. Task B：精确对账（完成）

- **912 SETTLED** = 24（canary）+ 2（早期 canary 中止）+ 13（run1）+ 180（run2）+ 693（final_resumed），按唯一 request_id 终态计。
- **699 行级尝试 = 693 proxy SETTLED + 1 UNKNOWN + 5 REJECTED**：207/208 行完全一致；唯一差异行 `micro-011-second_largest/B1-random`（IncompleteRead 中止行）的 6 次尝试对应 1 UNKNOWN + 5 gate-stopped REJECTED，proxy SETTLED=0。差额**全部解释**，无重复计费。
- **全轮费用** = 1.306339（SETTLED，peak）+ 0.157041（UNKNOWN 上界）= **1.463380 CNY < 2.00**。
- manifest 行数修正：`rows_total=208`、`rows_written_last_process=58`（原 manifest 字节与哈希 `c941c40b…` 保留）。
- 报告：`docs/PHASE4_R1_9_RECONCILIATION.md`（含精确公式与全部哈希）。

## D. Task C：算法真实性更正（完成）

- **R1.9 唯一 live evolve 事件实际调用 NSGA-III 选择 = 0 次**：4 已测量候选全部直接成为父母（`len(measured)=4 = n_parents`），且 8<16 无溢出，故父代/幸存者两个选择分支均未触发。
- 现在 evolve 事件显式记录 `nsga3_parent_selection_calls` / `nsga3_survivor_selection_calls`，并新增 3 项回归测试（恰好 4 已测量=0、>4=1、溢出=幸存者调用）。离线 NSGA-III 测试不受影响。
- 更正附注：`docs/PHASE4_R1_9_CORRECTION_ADDENDUM.md`；算法保真文档：`docs/PHASE4_R1_10_ALGORITHM_FIDELITY.md`。

## E. Task D：增量成本与 no-op 反馈（CEA-v2.1，完成）

- `run_row`：attempt 1 后快照，attempt 2 只将**增量成本/调用**传给控制器；行记录同时保留每次 attempt 成本与总量。
- no-op 表型：不重试但恰好观察一次（最终失败 + 0 增量成本/调用），infra 永不作为行为奖励。
- 控制器版本 `cea-v2.1-r1.10`；历史 R1.9 观察不追溯改写。
- 测试 `tests/test_incremental_fitness.py` **4/4**（增量排除 attempt-1、no-op 恰好一次、infra 不入统计、重放一致）。

## F. Task E：统计复核与簇级敏感性（完成）

- 从脱敏投影重算成功率、不一致对、McNemar、Holm、费用与 CI（与原 analysis 一致）；覆盖 26×2×4、键唯一、种子与任务哈希核对通过。
- 预注册 McNemar 结果**原样保留**；新增**事后**任务簇配对符号翻转置换检验（26 簇、两种子同簇、20000 次置换、seed 20261026）：
  - CEA-v2 vs B1-random：**p = 0.7462**
  - CEA-v2 vs B5-v1：**p = 0.62095**
  - CEA-v2 vs B0：**p = 0.7268**
  - 与预注册非显著结论一致，**探索性结论不变**。
- 产物：`results/phase4/r19-audit/sensitivity.json`。明确标注：McNemar 的 p 不是簇调整后的确认性证据；未来确认性协议必须使用簇感知主检验。

## G. Task F：状态与报告元数据（完成）

- `status.json`：无重复 `blockers` 键（仅 1 处）；planner_review/live_readiness/next_goal/当前 HEAD 更新为 R1.10 实际状态；R1.7/R1.9 历史审查记录保留。
- `docs/PHASE4_FORMAL_EXPERIMENT_REPORT.md` 的更正通过 `docs/PHASE4_R1_9_CORRECTION_ADDENDUM.md` 链接完成（证据缺失、manifest 行数、请求对账、NSGA-III 0 调用、整-episode 成本五项均明确）。

## H. 验证矩阵（实际命令与真实输出）

| 项 | 命令 | 结果 |
|---|---|---|
| 控制器（含 NSGA-III 调用计数） | `pytest tests/test_online_evolution.py -q` | 19 passed |
| 增量适应度/no-op | `pytest tests/test_incremental_fitness.py -q` | 4 passed |
| agent smoke | `pytest tests/test_cea_v2_integration.py -q` | 6 passed |
| 合成驱动 | `pytest tests/test_cea_v2_offline.py -q` | 14 passed |
| 预算四套件 | `pytest tests/test_budget_proxy{,_r14,_r15,_r16}.py -q` | 102 passed |
| 凭证/控制/e2e/适配器/v2 | 五文件联合 | 50 passed |
| 分析 | `pytest tests/test_analyze_r19.py -q` | 4 passed |
| **全量** | `pytest tests/ -q` | **623 passed / 0 failed / 0 skipped** |
| clean-clone（最终 SHA） | `python scripts/clean_clone_check.py` | 见末节 |

无 NOT_VERIFIED 项；Docker 全程可用。

## I. 费用与安全

- 本轮真实模型调用 **0 次**、费用 **¥0**；无余额查询。
- 历史 312 行与 Phase 0–3 冻结工件零改动；`calls.csv` `1961bdd8…`、`auditable_tasks.jsonl` `35b9e67a…`、sweep `15e2cb84…` 未变。
- 密钥扫描：`git diff --cached | grep -cE "sk-[A-Za-z0-9]{32}"` = 0。

## J. 未解决问题

1. R1.9 的 CEA-v2 无提升证据；本轮为证据/算法修复，未产生新的模型性能结果。
2. R1.9 的成本目标为整-episode 口径（已披露并仅在未来改为增量口径），不影响成功率统计结论。
3. Planner 未独立重跑本机测试；全部数字为 Executor 实际终端输出。
4. L4 递归自我改进仍未实现；未来确认性实验需簇感知主检验与新的用户预算授权。

## K. Git 交付（最终 SHA / clean-clone / 同步）

（push 后实测填写。）

## 停止

停在 Phase 4 R1.10。未进入付费 pilot 或 Phase 5。`next_actor = GPT-Planner`。
