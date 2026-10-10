# Executor Report — Plan CE-DSH-P0-R1.1（Phase 0 定向修复）

日期：2026-10-10。Executor：Kimi。本报告只含已实际运行的结果。
原始 100 条 live CSV 未改（SHA-256 `1961bdd8…e364c59`，测试锁定）；本轮零新增 live API 费用。

## 总览

- F1–F5 全部修复完成；测试 **64 passed / 0 failed / 0 skipped**（`pytest tests/ -q`，R1.1 后实际重跑）。
- 纠正后权威统计（由不可变 CSV 机器重算，与 Planner 独立审计一致）：
  uncached **27,316** / cache_read **29,184** / total_prompt **56,500** / output **3,833**；
  整体加权命中率 **0.51653**，逐请求均值 **0.45984**（两口径差异已说明）；
  finish_reason：completed 59 / max-tokens 41（A=25/0、B=12/13、C=15/10、D=7/18）。
- 费用：off-peak 估算 **¥0.0460417392**（peak 上界 ¥0.0920834784），属基于价格页与 FX 假设的估算值；`actual_billed_cost_cny = null`（unknown），visible_balance_delta = 0。
- 修复细节与证据：`docs/PHASE0_R1_1_FIX_REPORT.md`；机器校验：`results/phase0/live/reconciliation.json`（5 项校验全过）。

## 修复项状态

| 项 | 状态 | 证据 |
|---|---|---|
| F1 聚合一致性 | FIXED | aggregate_rows()、reconcile.py、reconciliation.json、summary.json 回填标注、tests/test_live_csv_consistency.py（7 项） |
| F2 未知计费 fail-closed | FIXED | benchmark.py 全 attempt 计量、unknown_cost 停机、local_rejected 例外、gate 按 attempt 上界；tests/test_failure_metering.py（5 项矩阵） |
| F3 API 成功 vs 任务有效 | FIXED | response_accepted / task_valid / response_sha16 三层；存量 100 条 task_valid=unknown 披露；tests/test_task_validity.py（4 项） |
| F4 配置哈希/脱敏 | FIXED | 白名单脱敏（max_tokens 等数值保留）；effective_config_fingerprint（含 patch SHA+SDK 版本+override 敏感）；authorized vs runtime 预算分离；legacy 哈希保留标注；tests/test_config_fingerprint.py（4 项） |
| F5 文档/状态一致性 | FIXED | RESULTS/AUDIT/executor_report/status 全部改用重算数字；估算值与 unknown 标注 |

## 验证记录

- `pytest tests/ -q` → 64 passed（含 CSV 一致性、失败计费矩阵、任务有效性、脱敏与指纹）。
- `--dry-run --run-id dryrun-r11` → 100/100 fake ok；离线、无需密钥。
- 原始 `results/phase0/live/calls.csv` 未修改；`summary.json` 由 CSV 无损回填并标注来源；新增 `reconciliation.json`。
- 未运行任何新 live 调用。

## 无法验证事项（如实声明）

1. 实际扣费金额 unknown（余额分辨率 0.01 CNY + 账单延迟）。
2. 存量 100 条的任务输出正确性 unknown（响应正文未持久化；其中 41 条 max-tokens 截断，确定不是完整任务输出）。
3. 工具禁用与 live 运行的 runtime 证据产生于本机执行环境；Planner 环境未复跑。

## 停止条件

停在 Phase 0。status.json 设为 READY_FOR_REVIEW，等待 GPT Planner 第二轮验收；不进入 Phase 1。
