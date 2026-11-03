# Executor Report — CE-DSH-P4-R1.12-REVIEW-FIX3（最终离线审计修复与验收）

日期：2026-10-29。Executor：Kimi。**本轮 0 次真实 DeepSeek 调用、¥0 新增费用；未重跑 live pilot/canary；未查询余额；未进入 Phase 5。**

计划：planner/latest_plan.md（CE-DSH-P4-R1.12-REVIEW-FIX3）；独立复审：planner/reviews/CE-DSH-P4-R1_12-review-fix2-independent-review.md。

## A. Git 状态

- 起始 SHA：`c007b5c64280bad53c5c6f272be961eca472e855`（与预期 Planner 状态提交一致，工作区 clean）
- 最终 SHA / 远端 SHA / clean-clone 验证 SHA：见末节「Git 交付」

## B. Task A：符号链接逃逸测试修复（完成）

`tests/test_r12_hashes.py` 的 symlink 用例现改为：在**真实允许工件根目录** `results/phase4/live2/` 内创建临时符号链接，指向根目录外的 `status.json`，构造 manifest 后实际调用验证器，断言其拒绝 symlink 逃逸（`escapes allowed artifact root`），并以 `try/finally` 清理临时链接与目录，避免污染仓库。

- 当前 Windows 账户无 symlink 创建权限：用例按平台限制 **skipped**（pytest.skip 记录原因），**未计为通过**。
- 已在 **Linux/WSL（Ubuntu-22.04, Python 3.10.12）实际执行**同一断言：验证器对 `results/phase4/live2/symlink-test-tmp/tasks.jsonl` 返回 exit 1，输出 `pilot_tasks: path escapes allowed artifact root`——symlink 逃逸拒绝已实证。
- 父级穿越、绝对路径、缺失文件、哈希不匹配、非法清单、畸形 sha256/条目等既有回归测试全部保留。

## C. Task B：Holm 映射回归测试非平凡化（完成）

- 新增纯函数 `holm_adjusted_by_key(p_by_key)`：按 `(raw_p, key)` 排序并计算 Holm step-down，**按原比较键返回调整值**（不依赖字典序）。
- 回归测试 `tests/test_holm_mapping.py` **4/4**：
  - 三个**互不相同**的原始 p 值，且原始 p 排序的键序**不同于字典键序**，每个调整值都映射回正确原键（含累计最大值、单调性、[0,1] 范围）。
  - 并列值与累计最大值处理正确。
  - 分析器只对三个预注册次要比较做 Holm 校正，主比较 `CEA-v2-online vs B1-random` **保持未校正**。
  - 反例守卫：按字典序错配会把最大调整值放到错误的键上（旧 bug 被显式排除）。
- 冻结统计定义、原始实验结果与预注册方案未改。

## D. Task C：状态文件与测试证据统一（完成）

- 全量实际命令 `pytest tests/ -q` 的真实输出：**665 passed / 0 failed / 1 skipped（exit 0）**。`status.json.tests.passed=665, failed=0, skipped=1`；`count_note` 记录该真实输出并注明 1 个 symlink 用例按平台限制跳过，及 Linux/WSL 的补充验证。
- `tests.categories.unit_integration_full_suite` 同步为同一真实结果（不再是旧 637/663/668 混杂值）。
- 区分：全量测试 665/0/1；专项测试（r12_hashes 9/1 skip、holm_mapping 4/0、analysis_determinism 2/0、frozen_task_set 9/0）；clean-clone 中关键套件 240/1 skip；平台限制跳过单独注明，不混为通过。
- `phase_status` 在最终门禁完成前保持 `CHANGES_REQUESTED`（不提前 READY），`next_actor=Kimi-Executor` 待门禁完成后改 `GPT-Planner`；`clean_clone_final=PENDING_FINAL_GATE` 待最终 SHA 门禁执行后据实记录。
- `tests.current_remote_head` 更新为最终提交 SHA（末节）；`clean_clone_tested_sha=e1df3bd…`（已测）与当前 pre-fix SHA `c436de…`（未测）明确区分。

## E. Task D：冻结数据与哈希完整性（完成）

- canonical task manifest SHA-256 = `fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`（与预注册一致）；26 任务、种子 `20261027,20261028`、4 臂、208 唯一 `(task_id,seed,arm)` 键，无缺失/重复/额外记录。
- `verify_r12_hashes.py`：**12 个必需工件全部通过**（重建 manifest 后哈希匹配）。
- 原始 R1.12 tasks/events/proxy-ledger 字节未改；历史 R1.9 与 Phase 0–3 冻结工件未改；历史 Monte Carlo 不可变来源与三条估计/provenance 未改（`previous_monte_carlo_estimates.json` SHA-256 `39a7d7829e28db7629db6881f84561be779ffb9d5ef14b3f9b088c598b578b1c`）。
- 累计账本复核：738 settled requests、CNY 1.0397171982、UNKNOWN bound 0，未通过新增 API 请求重建证据。

## F. 验证矩阵（实际命令与真实输出）

| 项 | 命令 | 结果 |
|---|---|---|
| 哈希验证器 | `pytest tests/test_r12_hashes.py -q` | 9 passed / 1 skipped（symlink 平台限制） |
| Holm 键映射 | `pytest tests/test_holm_mapping.py -q` | 4 passed |
| 分析确定性 | `pytest tests/test_analysis_determinism.py -q` | 2 passed |
| 冻结任务集 | `pytest tests/test_frozen_task_set.py -q` | 9 passed |
| R1.12 分析 | `pytest tests/test_analyze_r12.py -q` | 3 passed |
| 历史估计保留 | `pytest tests/test_cluster_sensitivity.py -q` | 9 passed |
| 累计预算对账 | `pytest tests/test_round_spend.py -q` | 2 passed |
| 控制器 | `pytest tests/test_online_evolution.py -q` | 19 passed |
| 增量适应度 | `pytest tests/test_incremental_fitness.py -q` | 4 passed |
| agent smoke | `pytest tests/test_cea_v2_integration.py -q` | 6 passed |
| 合成驱动 | `pytest tests/test_cea_v2_offline.py -q` | 14 passed |
| 预算四套件 | `pytest tests/test_budget_proxy{,_r14,_r15,_r16}.py -q` | 102 passed |
| 凭证/控制/e2e/适配器/v2 | 五文件联合 | 50 passed |
| **全量** | `pytest tests/ -q` | **665 passed / 0 failed / 1 skipped（exit 0）** |
| 工件哈希 | `python scripts/verify_r12_hashes.py` | `HASH VERIFIED: 12 artifacts` |
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
5. Windows 上 symlink 用例按平台限制跳过（未计为通过）；已在 Linux/WSL 补充验证 symlink 逃逸拒绝。

## I. Git 交付（精确最终 SHA / clean-clone / 同步）

（push 后实测填写；最终门禁后不再提交，结果以本条与最终回复为准。）

## 停止

停在 Phase 4 R1.12-REVIEW-FIX3。未进入 Phase 5。`next_actor = GPT-Planner`（门禁完成后）。
