# Executor Report — CE-DSH-P4-R1.12-REVIEW-FIX2（离线审计修复与最终验收）

日期：2026-10-28。Executor：Kimi。**本轮 0 次真实 DeepSeek 调用、¥0 新增费用；未重跑 live pilot/canary；未查询余额；未进入 Phase 5。**

计划：planner/latest_plan.md（CE-DSH-P4-R1.12-REVIEW-FIX2）；独立复审：planner/reviews/CE-DSH-P4-R1_12-review-fix1-independent-review.md。

## A. Git 状态

- 起始 SHA：`c436de3086c31c6f7bdb21a32c83b06b7c173ed4`（与预期一致，工作区 clean）
- 最终 SHA / 远端 SHA / clean-clone 验证 SHA：见末节「Git 交付」

## B. Task A：哈希验证器加固（完成）

`scripts/verify_r12_hashes.py`：

- 路径包含校验改为 **Path.relative_to 针对具体工件根目录**（results/phase4/live2、docs、scripts），不再仅检查 REPO 前缀或字符串前缀。拒绝：绝对路径、父级穿越、**symlink 逃逸**（resolve 后离开工件根目录）、非允许根路径。
- **强制精确工件清单**：必须恰好 12 个必需标签；缺失标签、意外标签、非对象条目、非 64 位十六进制 sha256 均拒绝。
- 回归测试 `tests/test_r12_hashes.py` **9 passed / 1 skipped**（symlink 用例在当前 Windows 账户无创建权限，按平台限制跳过，未计为通过）。通过、父级穿越到 status.json、绝对路径、symlink 逃逸、缺必需标签、意外标签、畸形 sha256、畸形条目、缺失文件、哈希不匹配全部按预期拒绝/通过。

## C. Task B：Holm 调整值与比较键映射修正（完成）

- 现在按 `(raw_p, comparison_key)` 对排序并计算 Holm step-down，再**回写到原比较键**（保留 raw p 与键的对应关系，字典序不同的非平凡 p 值也不会错配）。
- 主比较 `CEA-v2-online vs B1-random` 保持未校正；仅三个次要比较进入 Holm 家族（累计最大值、单调不减）。
- 集成测试 `tests/test_holm_mapping.py` **2/2**：非平凡 p 值下每个比较键都得到其数学上正确的 Holm 调整值；主比较不进入次要家族。

## D. Task C：analysis.json 稳定相对路径与确定性（完成）

- `run_dir` 现在：在仓库内为 `results/phase4/live2/<run_id>` 的 POSIX 相对路径；在仓库外为稳定的 run 目录名（不再写入机器相关的 Windows 绝对路径）。
- 对现有 R1.12 原始数据重跑分析：两次输出 `analysis.json` 的 SHA-256 完全一致（`fb6387ce333722be730fed4c5d692af00c1ae051073c6aad7018432cb56f4ba9`）。
- 确定性测试 `tests/test_analysis_determinism.py` **2/2**：两个隔离输出位置产出**字节一致**的 analysis.json；run_dir 为相对 POSIX 路径而非机器绝对路径。
- 已重建 `manifest_reconciled.json` 并 `HASH VERIFIED: 12 artifacts`。
- 原始 tasks/events/proxy-ledger 字节未改。

## E. Task D：状态与报告归一（完成）

- `status.json`：`phase_status=READY_FOR_REVIEW`、`next_actor=GPT-Planner`、`baseline_main_sha=c436de…`（pre-fix 基线）、`reviewed_executor_head` 记录最终提交 SHA（末节）；`clean_clone_tested_sha=e1df3bd…`（已测）与当前 pre-fix SHA `c436de…`（未测）明确区分；`clean_clone_final=PENDING_FINAL_GATE`（最终门禁执行前不写 PASS）。
- `tests.current_remote_head` 更新为最终提交 SHA（末节）；`live_readiness=STOPPED_AT_PHASE4`（不再继续 live、禁止 Phase 5）。
- 历史 R1.9 与 Phase 0–3 冻结工件、历史 Monte Carlo 不可变来源与三条估计/provenance 均未改动。

## F. 验证矩阵（实际命令与真实输出）

| 项 | 命令 | 结果 |
|---|---|---|
| 哈希验证器 | `pytest tests/test_r12_hashes.py -q` | 9 passed / 1 skipped（symlink 平台限制） |
| Holm 键映射 | `pytest tests/test_holm_mapping.py -q` | 2 passed |
| 分析确定性 | `pytest tests/test_analysis_determinism.py -q` | 2 passed |
| R1.12 分析 | `pytest tests/test_analyze_r12.py -q` | 3 passed |
| 冻结任务集 | `pytest tests/test_frozen_task_set.py -q` | 9 passed |
| 历史估计保留 | `pytest tests/test_cluster_sensitivity.py -q` | 9 passed |
| 累计预算对账 | `pytest tests/test_round_spend.py -q` | 2 passed |
| 控制器 | `pytest tests/test_online_evolution.py -q` | 19 passed |
| 增量适应度 | `pytest tests/test_incremental_fitness.py -q` | 4 passed |
| agent smoke | `pytest tests/test_cea_v2_integration.py -q` | 6 passed |
| 合成驱动 | `pytest tests/test_cea_v2_offline.py -q` | 14 passed |
| 预算四套件 | `pytest tests/test_budget_proxy{,_r14,_r15,_r16}.py -q` | 102 passed |
| 凭证/控制/e2e/适配器/v2 | 五文件联合 | 50 passed |
| **全量** | `pytest tests/ -q` | **663 passed / 0 failed / 0 skipped** |
| clean-clone（精确最终 SHA） | `python scripts/clean_clone_check.py <sha>` | 见末节 |

无 NOT_VERIFIED 项（除已声明的平台 symlink 跳过）；Docker 全程可用。

## G. 费用与安全

- 本轮真实模型调用 **0 次**、新增费用 **¥0**；未重跑 live；未查询余额。
- 历史 R1.9 与 Phase 0–3 冻结工件未改；R1.12 原始 tasks/events/proxy-ledger 字节未改。
- 密钥扫描：`git diff --cached | grep -cE "sk-[A-Za-z0-9]{32}"` = 0；累计费用账本与 manifest 对账一致（738 settled requests、CNY 1.0397171982、UNKNOWN bound 0）。

## H. 未解决问题

1. CEA-v2 相对随机/静态基线无提升证据（主比较差 0、p=1.0、CI 跨 0）；NSGA-III 父代/幸存者调用均为 0，**算法选择机制尚未被真实实验验证**。
2. 仅 5 条行为观察，不能据此声称控制器已学到可靠选择策略；L4 RSI 未实现。
3. 同任务集新种子复制，非未见任务泛化。
4. Planner 未独立重跑本机测试；数字为 Executor 实际终端输出。

## I. Git 交付（精确最终 SHA / clean-clone / 同步）

- **REVIEW-FIX2 主提交：`4349161eace78db9988a6add27fae7960e8df943`**（push 后 `git ls-remote origin main` 与本地 HEAD 一致）。
- **最终 SHA Gate（逐字输出）**：
  ```
  verified: 312 auditable rows recompute to the committed analysis (incl. cluster bootstrap)
  34 passed in 3.82s (phase4 subset)
  240 passed, 1 skipped in 380.55s (key suites incl. r12_hashes, holm_mapping, analysis_determinism)
  CLEAN CLONE OK: HEAD 4349161eace7 == origin/main; 312 auditable rows recompute in a fresh clone
  exit=0
  ```
- **clean-clone 验证 SHA（完整）**：`4349161eace78db9988a6add27fae7960e8df943`（脚本强制 clone HEAD == ls-remote，失配 exit 2；命令行显式传入该 SHA）。
- 本记录提交（housekeeping）仅改 status.json 与 executor_report.md，不含代码/测试变更；按 Planner 要求，最终门禁后不再做任何提交，Gate 结果以本条与最终回复为准。
- 同步状态：本地 HEAD == `git ls-remote origin main`；`git status --porcelain` = 0（clean）。
- 冻结校验：staged diff 中 results/phase0–3 与 results/phase4/live 零改动；密钥扫描 0 命中。

## 停止

停在 Phase 4 R1.12-REVIEW-FIX2。未进入 Phase 5。`next_actor = GPT-Planner`。
