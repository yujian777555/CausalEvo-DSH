# CE-DSH-P4-R1.5 — Remediation Evidence（跨类型别名校验 / 账本严格数值校验 / 证据统一）

日期：2026-10-20。Executor：Kimi。本轮**新增 DeepSeek 模型 API 调用 0 次、费用 ¥0**；未运行 `--live`；未查询真实余额。

计划：planner/latest_plan.md（CE-DSH-P4-R1.5）；审查：planner/reviews/CE-DSH-P4-R1_4-independent-review.md。

## P0-A：输出 token 双字段跨类型相等绕过

根因（审查 P0-A）：R1.4 的 `_output_limit_problem` 先比较 `mt != mct` 再校验有效字段，且有效字段取 `max_tokens` 优先。Python 跨类型相等（`True == 1`、`256.0 == 256`）使以下请求通过校验并转发上游：

```json
{"max_tokens": 1, "max_completion_tokens": true}
{"max_tokens": 256, "max_completion_tokens": 256.0}
```

修复（`budget_proxy.py`）：

- 新增 `_strict_positive_int(v)`：`isinstance(v, int) and not isinstance(v, bool) and v > 0`；float/str/null 永不通过。
- `_output_limit_problem`：先对**每个实际提供的字段独立**严格校验，任何字段非法即 `output_limit_illegal`；两者均通过后才比较整数值一致性（不一致 `output_limit_ambiguous`）；均缺失 `output_limit_missing`。
- 不依赖跨类型相等证明合法性；拒绝全部发生在预算预留与上游发送之前，不消耗预算协议不变。

测试（tests/test_budget_proxy_r15.py；修复前 6 failed 含 planner 给出的两个绕过样本）：

- 4 组混型对（两个方向）+ 12 组单字段非法（bool/float/str/null/zero/负 × 两别名）+ 双缺失 + 合法整数冲突：全部 400/403，Fake Provider `call_count == 0`，`per_scope` 为空，`states` 无预留，账本只有 REJECTED 审计。
- 正向：单字段合法、等值合法对 (64,64)、边界 == cap(2048) 通过；cap+1 拒绝；上游计数 3。

## P0-B：账本金额严格校验（初始 + 重复事件）

根因（审查 P0-B）：重复 SETTLED 分支只做 `isinstance(new,(int,float)) and abs(old-new) > 1e-12`——`bool` 是 `int` 子类（`True` 可当金额 1 通过），`NaN` 使容差比较恒为 False（`abs(nan-x) > tol == False`），非法重复被幂等吞掉。初始 RESERVED/SETTLED 同样接受 bool 金额。

修复：

- 共享校验器 `_valid_amount(v)`：数值类型、非 bool、`math.isfinite`、≥ 0。
- 初始 RESERVED（reserved_cny）、初始 SETTLED（cost_cny）、重复 RESERVED、重复 SETTLED 全部统一使用该校验；重复事件只有在语义字段**合法且完全相等**时才幂等（不再对未校验数值做差值容差比较）。
- 非法/冲突金额 → `ledger_corrupt` → fail-closed（停止并拒绝新请求）；账本文件永不自动改写或修复。
- 重放对 reconcile 事件的既有校验不变；合法历史、崩溃恢复、幂等重复全部保持。

测试（真实账本文件经正式重放入口）：

- 重复 SETTLED：NaN / Infinity / bool / 负数 / 冲突合法金额 → corrupt；相同合法金额 → 幂等且历史费用恰好恢复一次。
- 初始 SETTLED：NaN / Infinity / bool / 负 → corrupt。
- 初始 RESERVED：bool / NaN / Infinity / 负 → corrupt。
- 重复 RESERVED：bool / NaN / Infinity / 负 / 冲突金额 → corrupt（合法完全重复幂等由 r14 套件保持）。
- 损坏账本：新请求 429、账本文件 0 追加（无自动修复）、重启后仍 fail-closed。
- 合法历史（settled + 崩溃恢复 + scoped reconcile）重放与恢复不受影响。

## P1-C：全量测试计数统一（523 vs 525 的实际原因）

事实链（两次 R1.4 全量运行的真实终端输出）：

- 运行 1（bash 日志）：`2 failed, 523 passed in 564.60s`（收集 525；失败 2 项：direct_connect 请求体缺 max_tokens 被新严格校验拒绝、e2e cap 测试 docker 时序 flake）。
- 修复两处**测试体**（补 max_tokens、e2e wall_time 240→480s，未新增/删除任何测试）后运行 2：`525 passed in 595.58s`。
- executor_report.md 表格取自运行 1 的 passed 数（523）且未随运行 2 更新；status.json 已更新为 525——两文件引用了不同运行的结果，造成矛盾。

本轮：对当前源码（含 R1.5 新增 42 项）执行规定命令 `pytest tests/ -q`，逐字保存摘要（见 planner/executor_report.md），status.json 与报告统一为同一真实数字。

## P1-D：最终 SHA Clean-clone Gate

按修正流程执行：全部修复提交 → 推送 → 读取 `git ls-remote origin main` 完整 SHA → `scripts/clean_clone_check.py`（脚本强制 clone HEAD == ls-remote，不一致 exit 2）→ clone 内复算（312 行）+ phase4 子集 + 7 关键套件 → 逐字输出与退出码记录于报告。记录提交（docs-only）按 P1-D 明确标注其 Gate 覆盖关系，不再出现"两个 SHA 都说成已验证"。

## P1-E：冻结数据与工件来源（精确口径）

1. **历史 Phase 4 live 312 行数据与已跟踪冻结文件**：未变。证据：`git log` 显示 `results/phase4/live/` 与 `results/phase0/` 最后变更提交分别为 45a0bd2（R1.1）、e7656bd（P4）、d1bb542（P0-R1.2），R1.3–R1.5 无任何提交触碰；`results/phase0/live/calls.csv` SHA-256 = `1961bdd8…`（与 status.json 记录一致）；`auditable_tasks.jsonl` SHA-256 = `35b9e67a…`；`git diff 9b1abcb..HEAD -- results/ benchmarks/` 仅 3 个文件（见下）。
2. **此前被忽略、R1.4 新纳入版本控制的 Phase 3 工件**：`results/phase3/replay_sweep/sweep_results.jsonl`（42 行，33KB）。原始本地工件仍可访问：工作区原始字节 SHA-256 = `15e2cb844584398d5ce2e65c4ccb1c5bf6be052ab6436cee75815e14e4540ab4`（CRLF）；入库 blob SHA-256 = `564f7d18927bcc2b485fbab8cb2d858d66a54dec31912d13a3b894baa7f77262`（core.autocrlf=true 提交时 CRLF→LF 规范化）；`cmp` 原始 vs blob：**字节在第 807 字节起不同（仅换行符）**；LF 规范化后 `cmp` **完全一致**。即：内容逐行相同，差异仅为换行符；不存在信息改写。
3. **规范化哈希如何工作**：`canonical_sha256(path)` 读取字节后将 `CRLF/CR → LF` 再计算 SHA-256，使"同一工件"在 Windows 工作区与干净 clone 中得到同一哈希；它不改变工件内容本身，只定义与平台换行符无关的身份。`configs/phase3_artifact_manifest.json`、`src/causalevo/evolution/adapter.py`、`scripts/run_phase4_v2_offline.py` 的修改正是为此（R1.4 最终 SHA Gate 实测发现）——这三处是可复现性装载代码/清单的变更，不属于实验数据。
4. v2-offline 运行目录（results/phase4/v2-offline/run-20261020T104048Z）为 fake-provider 适配器 smoke 证据，非历史真实数据。

不为表面零差异删除任何复现工件；sweep 工件保留在版本控制中。

## 边界

本轮 0 次真实模型调用、¥0；全部测试为 fake provider/离线；Docker 测试在本机真实执行（daemon 29.3.1 可用，无 NOT_VERIFIED 项）。
