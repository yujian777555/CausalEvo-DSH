# Executor Report — CE-DSH-P4-R1.11-FIX1 + R1.12（历史估计修复 + 新种子复制实验）

日期：2026-10-27。Executor：Kimi。R1.11-FIX1 离线修复后，按预注册协议执行 R1.12 真实 DeepSeek 复制实验（用户授权，累计硬上限 ¥2.00）。

## A. Git 状态

- 起始 SHA：`97374605644a3454e20ede523db1ca4f47a26241`（与预期一致，工作区 clean）
- FIX1/协议/runner 提交：`fec54f2a56ffa446e5e25d221d2ce1813caae8b0`
- 最终 SHA / 远端 SHA / clean-clone 验证 SHA：见末节「Git 交付」

## B. R1.11-FIX1（历史估计恢复，离线）

- 根因：生成器把生成的 `sensitivity.json` 当作历史估计来源，第二次重生成时 `previous_monte_carlo_estimates` 被覆盖为 `{}`。
- 修复：新增不可变来源 `results/phase4/r19-audit/previous_monte_carlo_estimates.json`（provenance 至 `2bb9e5c`），生成器只从该不可变文件读取三条历史估计，不再从生成物读取。
- 测试 `tests/test_cluster_sensitivity.py` **9/9**：两条历史记录逐字段（p/stat/20000/seed）在两次重生成后完整保留且字节一致；精确 DP p 值不变（0.75 / 0.625 / 0.7265625 / 1.0）。
- `manifest_reconciled.json` 的 script/output SHA-256 已更新；`status.json` 元数据归一（632 测试 Executor-reported）。
- **FIX1 clean-clone：PASS at `fec54f2a56ff`**（34 phase4 子集 + 209 关键套件，exit=0）。

## C. R1.12 预注册与门禁（live 前全部通过）

- 协议 `docs/PHASE4_R1_12_REPLICATION_PROTOCOL.md` 已提交：26 任务、种子 `20261027,20261028`、四臂 208 行、final_success 主终点、精确簇符号翻转 + 10,000 簇 bootstrap、提升判定（差值≥+0.10 且 p<0.05 且 CI>0）、累计 ¥2.00（预警 ¥1.80）、UNKNOWN fail-closed、禁止余额查询。
- runner：`--seeds` / `--run-tag`（历史默认保留）；累计预算 `_round_spend`（canary/中断/续跑均扣减，不重置）；2 个离线对账测试。
- 环境：docker 29.3.1、密钥仅经受控环境入 Proxy（agent 仅 per-run token）、TUN 关闭、直连路径未变、fake-provider E2E 6/6。
- canary：8 行全成功、0 UNKNOWN、费用 ¥0.029226，账本对账通过后进入完整复制。

## D. R1.12 真实复制实验（完成，208/208 行）

- 目录：`results/phase4/live2/phase4-r12-replication-pilot-20261027T034229Z`（canary：`…canary-20261027T034020Z`）。
- 全部 208 行完成，`aborted=None`；无 UNKNOWN、无截断、无重试不确定请求。
- 真实请求：canary 24 + 正式 714 = **738 次**（SETTLED 计）。
- 费用：canary ¥0.029226 + 正式 ¥1.010491 = **¥1.039717（peak 口径）**，远低于 ¥2.00 上限。

## E. 结果（探索性同套新种子复制）

| 臂 | 最终成功率 | off-peak 费用 | 请求数 |
|---|---|---|---|
| B0-original | 0.8846 | ¥0.116534 | 163 |
| B1-random | 0.9423 | ¥0.134121 | 192 |
| B5-v1-frozen-pareto | 0.9231 | ¥0.127357 | 179 |
| CEA-v2-online | 0.9423 | ¥0.127234 | 180 |

主比较与次要比较（`analysis.json`）：

| 比较 | 配对差 | 精确簇 p | 95% CI | Holm p | 提升证据 |
|---|---|---|---|---|---|
| CEA-v2 vs B1-random | 0.000 | 1.0 | [−0.077, 0.077] | 1.0 | 无 |
| CEA-v2 vs B5-v1 | +0.019 | 1.0 | [0.000, 0.058] | 1.0 | 无 |
| CEA-v2 vs B0 | +0.058 | 0.53125 | [−0.038, 0.173] | 1.0 | 无 |
| B5-v1 vs B1 | −0.019 | 1.0 | [−0.115, 0.058] | 1.0 | 无 |

- 在线更新：5 条行为观察、5 个选中基因组、population_version {0,1}。
- **NSGA-III 调用计数：evolve_events=1、parent_selection_calls=0、survivor_selection_calls=0**（4 已测量候选直接成为父母、无溢出；与 R1.9 同型）。**不声称 NSGA-III 已被验证**；live 仅执行交叉/变异/种群更新。
- 与 R1.9 结论一致：CEA-v2 相对随机/静态基线**无提升证据**；未宣称 L4 RSI。

## F. 验证矩阵（实际命令与真实输出）

| 项 | 命令 | 结果 |
|---|---|---|
| 敏感性/历史估计 | `pytest tests/test_cluster_sensitivity.py -q` | 9 passed |
| 累计预算对账 | `pytest tests/test_round_spend.py -q` | 2 passed |
| R1.12 分析 | `pytest tests/test_analyze_r12.py -q` | 3 passed |
| 控制器 | `pytest tests/test_online_evolution.py -q` | 19 passed |
| 增量适应度 | `pytest tests/test_incremental_fitness.py -q` | 4 passed |
| agent smoke | `pytest tests/test_cea_v2_integration.py -q` | 6 passed |
| 合成驱动 | `pytest tests/test_cea_v2_offline.py -q` | 14 passed |
| 预算四套件 | `pytest tests/test_budget_proxy{,_r14,_r15,_r16}.py -q` | 102 passed |
| 凭证/控制/e2e/适配器/v2 | 五文件联合 | 50 passed |
| **全量** | `pytest tests/ -q` | **637 passed / 0 failed / 0 skipped** |
| clean-clone（精确最终 SHA） | `python scripts/clean_clone_check.py <sha>` | 见末节 |

无 NOT_VERIFIED 项；Docker 全程可用。

## G. 费用与安全

- 本轮新实验真实调用 **738 次**；结算费用 **¥1.039717**；UNKNOWN 上界 **¥0**。
- 历史 R1.9 数据未修改；Phase 0–3 冻结工件未改；密钥扫描 `git diff --cached | grep -cE "sk-[A-Za-z0-9]{32}"` = 0；真实 key 未入 Agent 容器/argv/Git/日志。
- 未查询账户余额；未超过 ¥1.80 预警线（本轮 settled 远低于预警）。

## H. 未解决问题

1. CEA-v2 相对随机/静态基线无提升证据（与 R1.9 一致）；学习信号稀疏（仅 5 行为观察/52 行）。
2. NSGA-III 在两次 live pilot 中均为 0 调用，**算法选择机制本身尚未被真实实验验证**（离线测试验证其实现）。
3. 探索性同套复制：26 簇功效有限，不作论文级确认性结论或未见任务泛化宣称。
4. Planner 未独立重跑本机测试；数字为 Executor 实际终端输出。

## I. Git 交付（精确最终 SHA / clean-clone / 同步）

（push 后实测填写。）

## 停止

停在 Phase 4 R1.12。未进入 Phase 5。`next_actor = GPT-Planner`。
