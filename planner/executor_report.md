# Executor Report — CE-DSH-P4-R1.5（跨类型别名校验 / 账本严格数值校验 / 证据统一）

日期：2026-10-20。Executor：Kimi。本轮**新增真实 DeepSeek 模型 API 调用 0 次、费用 ¥0**；未运行 `--live`、未查询真实余额、未使用真实密钥发请求。

计划：planner/latest_plan.md（CE-DSH-P4-R1.5）；审查：planner/reviews/CE-DSH-P4-R1_4-independent-review.md。证据文档：docs/PHASE4_R1_5_REMEDIATION.md。

## A. Git 状态

- 起始 SHA：`d9fbfa2697eb68f760fd3c9c2813376cbda679f8`（接管时工作区 clean，0 未提交改动）
- 最终 SHA / 远端 SHA / 同步状态：见末节「Git 交付」（P1-D 流程：最终 push 后读取 ls-remote 并对该精确 SHA 执行 clean-clone Gate）

## B. P0-A：输出 Token 双字段类型校验漏洞（PASS）

- **根因**：R1.4 先比 `mt != mct` 再校验有效字段（且 max_tokens 优先）；`True == 1`、`256.0 == 256` 的跨类型相等使 `{max_tokens:1, max_completion_tokens:true}`、`{max_tokens:256, max_completion_tokens:256.0}` 通过校验。
- **修复**：`_strict_positive_int(v)`（真 int、非 bool、>0）；`_output_limit_problem` 对**每个实际提供字段独立**严格校验后再比较整数一致性；拒绝在预算预留与上游发送之前。
- **新增测试**：tests/test_budget_proxy_r15.py 20 项别名用例（4 混型对 + 12 单字段非法 + 双缺失 + 冲突合法整数 + 正向边界组）。
- **修复前失败证据**：`tests/test_budget_proxy_r15.py` 首次运行 `6 failed, 36 passed`（失败含 planner 指出的两个绕过样本、重复 SETTLED NaN、初始 bool 金额）。
- **修复后结果**：20/20 通过；非法请求 Fake Provider 实际接收计数逐项 = 0；`per_scope` 与 `states` 为空；账本仅含 REJECTED 审计。
- 正向：单字段合法、(64,64) 等值对、边界 ==cap 通过（上游计数 3）；cap+1 拒绝。

## C. P0-B：账本重复事件严格数值校验（PASS）

- **根因**：重复 SETTLED 分支仅 `isinstance + abs diff`；`True` 属 int 子类可当金额；`NaN` 使容差比较恒 False → 非法重复被幂等接受。初始 RESERVED/SETTLED 同样接受 bool。
- **修复**：共享 `_valid_amount(v)`（数值、非 bool、有限、≥0），统一用于初始/重复的 RESERVED 与 SETTLED；重复事件仅当语义字段合法且完全相等时幂等；非法/冲突 → `ledger_corrupt` → fail-closed；账本文件永不自动改写。
- **新增测试**：22 项账本用例（重复 SETTLED NaN/Inf/bool/负/冲突、初始 SETTLED NaN/Inf/bool/负、初始 RESERVED bool/NaN/Inf/负、重复 RESERVED bool/NaN/Inf/负/冲突、相同合法重复幂等、损坏账本拒绝新请求+文件 0 追加+重启仍 fail-closed、合法历史重放与崩溃恢复保持）。
- **修复后结果**：`pytest tests/test_budget_proxy.py tests/test_budget_proxy_r14.py tests/test_budget_proxy_r15.py -q` → **94 passed / 0 failed**（含 r14 全部既有恢复/对账回归）。

## D. P1-C / P1-D / P1-E

### P1-C：全量计数统一

- 不一致实际原因：R1.4 全量**两次**运行——运行 1 `2 failed, 523 passed`（收集 525；direct_connect 请求体缺 max_tokens + e2e docker 时序 flake）；修复两处测试体（不增删测试）后运行 2 `525 passed`。报告表格停留在运行 1 的 523，status.json 更新为 525。
- 本轮统一：对当前源码（含 R1.5 新增 42 项）执行 `pytest tests/ -q`，真实摘要：
  - 运行 1：`1 failed, 566 passed in 660.88s`（test_proxy_key_delivered_via_env_not_argv 在全量负载下 docker 时序超时；单跑 3/3 通过）。
  - 操作级超时加固（proxy 就绪 45→120s、控制 ACK 10→30s；不触碰任何断言）后运行 2：`567 passed in 564.77s` / 0 failed / 0 skipped（最终统一值）。
- status.json 与本报告使用同一运行 2 数字。

### P1-D：最终 SHA Clean-clone Gate

流程：修复提交 → push → `git ls-remote origin main` 完整 SHA → `scripts/clean_clone_check.py`（强制 clone HEAD == ls-remote）→ clone 内复算 + phase4 子集 + 7 关键套件。逐字输出/退出码/SHA：见末节「Git 交付」。

### P1-E：冻结数据与工件来源

- **312 行历史 live 数据与已跟踪冻结文件**：未变。`git log` 显示 `results/phase4/live/`、`results/phase0/` 最后被 R1.1/P4/P0-R1.2 提交触碰；`calls.csv` SHA-256 = `1961bdd81a7f6a4ad4169d6f246530ed3df3170f70948f85de13ca136e364c59`（与记录一致）；`auditable_tasks.jsonl` SHA-256 = `35b9e67a418cfd55fd9e820ab48980750da7ab12d24bc61392768f24b27e4afa`；`git diff 9b1abcb..HEAD -- results/ benchmarks/` 仅 3 文件（sweep 工件新增 + v2-offline 证据目录重生成）。
- **新入库 Phase 3 工件**：`results/phase3/replay_sweep/sweep_results.jsonl`（42 行）。原始本地工件可访问：原始字节 SHA-256 = `15e2cb844584398d5ce2e65c4ccb1c5bf6be052ab6436cee75815e14e4540ab4`（CRLF）；入库 blob SHA-256 = `564f7d18927bcc2b485fbab8cb2d858d66a54dec31912d13a3b894baa7f77262`；`cmp` 原始 vs blob 第 807 字节起不同（仅换行符），LF 规范化后 `cmp` 完全一致——内容逐行相同，无信息改写。
- **规范化哈希**：`canonical_sha256` 对 LF 规范化字节取 SHA-256，使工件身份与平台换行符无关；不改变工件内容。manifest/adapter/driver 的修改即为此（R1.4 Gate 实测发现的两个缺陷之修复）。

## E. 验证矩阵（实际命令与真实结果）

| # | 命令 | 结果 | 备注 |
|---|---|---|---|
| 1-2 | `pytest tests/test_budget_proxy_r15.py -q` | 42 passed | 别名 20 + 账本 22（修复前 6 failed） |
| 3-4 | `pytest tests/test_budget_proxy.py tests/test_budget_proxy_r14.py -q` | 52 passed | 既有回归全保持 |
| 5 | `pytest tests/test_credential_isolation.py -q` | 9 passed | — |
| 6 | `pytest tests/test_proxy_control.py -q` | 8 passed | — |
| 7 | `pytest tests/test_proxy_integration_e2e.py -q` | 7 passed | Docker 真实 |
| 8 | `pytest tests/test_causal_policy_adapter.py -q` | 19 passed | — |
| 9 | `pytest tests/test_phase4_v2_offline.py -q` | 7 passed | Docker 真实 |
| 10 | `pytest tests/ -q`（运行 1） | 566 passed / 1 failed | flake 项单跑 3/3 通过 |
| 10 | `pytest tests/ -q`（运行 2，超时加固后） | **567 passed / 0 failed / 0 skipped** | 全量最终统一值 |
| 11 | `python scripts/clean_clone_check.py`（最终 SHA） | 见 Git 交付节 | 强制 HEAD==ls-remote |
| 12 | 冻结 diff 审计 | 仅 sweep 工件新增 + v2 证据目录 | 见 P1-E |
| 13 | 密钥扫描 `git diff --cached | grep -cE "sk-[A-Za-z0-9]{32}"` | 0 | — |
| 14 | `git ls-remote origin main` vs 本地 HEAD / `git status --porcelain` | 见 Git 交付节 | — |

Docker daemon 29.3.1 与所需镜像全程可用：无 NOT_VERIFIED 项。

## F. 费用与安全

- 新增真实模型调用：**0 次**；新增费用：**¥0**；未发起任何真实 API 请求；未运行 `--live`；未设置 `CE_DSH_LIVE_AUTH`。
- 密钥扫描：0 命中；提交、日志、报告中无真实密钥。
- 未解决安全风险：见 G。

## G. 未解决问题

1. TUN 级 DeepSeek 直连仍为 `DIRECT_ROUTE_UNVERIFIED`（本轮 0 live 调用，无法实测）。
2. 全量运行 1 出现 1 项 docker 时序 flake（e2e key 送达测试；单跑 3/3 通过）；已将操作级超时加固（就绪 120s / ACK 30s），运行 2 结果见验证矩阵。该 flake 机制为负载下容器启动慢，非断言问题。
3. `docker inspect` Config.Env 对本机特权用户可见（宿主信任边界，已注明）。
4. Planner 未在本机独立重跑测试；所有数字为 Executor 实际执行输出。

## H. Git 交付（最终 SHA / clean-clone / 同步状态）

- **R1.5 主提交：`171e070892228f7cc7a2f8dd6d8f0de5642a25f9`**（修复+测试+文档）；clone 套件补充提交：`63e80e894c08a8bb90d5e006d96d5c3cbc740bbb`（clean_clone_check.py 增加 test_budget_proxy_r15）。
- **最终 SHA Gate（逐字输出）**：
  ```
  verified: 312 auditable rows recompute to the committed analysis (incl. cluster bootstrap)
  34 passed in 5.88s (phase4 subset)
  144 passed in 265.72s (credential_isolation 9 + budget_proxy 27 + budget_proxy_r14 25
      + budget_proxy_r15 42 + proxy_control 8 + proxy_integration_e2e 7
      + causal_policy_adapter 19 + phase4_v2_offline 7)
  CLEAN CLONE OK: HEAD 63e80e894c08 == origin/main; 312 auditable rows recompute in a fresh clone
  exit=0
  ```
- **Gate 验证 SHA（完整）**：`63e80e894c08a8bb90d5e006d96d5c3cbc740bbb`（= 执行 Gate 时的 origin/main 与本地 HEAD；脚本强制一致，失配 exit 2）。
- 本记录提交（housekeeping）仅改 status.json 与 executor_report.md，不含代码/测试变更；按 P1-D 如实声明：Gate 在 `63e80e8…` 通过，记录提交本身未再触发 Gate（如需可用 `python scripts/clean_clone_check.py` 随时对当前 HEAD 重验）。
- 同步状态：本地 HEAD == `git ls-remote origin main`；`git status --porcelain` = 0（clean）。
- 冻结校验：staged diff 中 results/phase0–3 与 results/phase4/live 既有跟踪文件零改动（R1.4 已披露的 sweep 工件为唯一新增，见 P1-E）；密钥扫描 0 命中。

## 停止

停在 Phase 4 R1.5。未进入付费 pilot，未进入 Phase 5。
