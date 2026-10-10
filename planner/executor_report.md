# Executor Report — Plan CE-DSH-P0-R1.2（Phase 0 计量闭环修复）

日期：2026-10-10。Executor：Kimi。本报告只含已实际运行的结果。
原始 100 条 live CSV 未改（SHA-256 `1961bdd8…e364c59`）；本轮**零新增 live API 调用**。

（R1.1 及更早内容见 git 历史；本节为当前轮。）

## 总览

- F2.1 / F2.2 两项计量缺口均修复；测试 **79 passed / 0 failed / 0 skipped**（R1.2 后实际重跑，64 → 79）。
- 历史数字不变（reconcile 重跑确认）：uncached 27,316 / cache_read 29,184 / total_prompt 56,500 / output 3,833 / 加权命中率 0.5165309734513275 / off-peak 估算 ¥0.0460417392。
- 费用：`actual_billed_cost_cny = null`（unknown）维持不变；存量 task_valid=unknown 维持；41 条 max-tokens 披露维持。

## 修复项状态

| 项 | 状态 | 证据 |
|---|---|---|
| F2.1 全 attempt 桶累计 | FIXED | benchmark.py `_row` 新增 `*_all_attempts` 计费列 + `final_attempt_usage` 专字段；aggregate_rows/reconcile 统一用 all-attempts；test_retry_success_meters_both_attempts 现断言输入桶双 attempt 累计；新增 test_two_metered_failures_both_bill（peak/off_peak 双口径） |
| F2.2 assistant/attempt 解析 | FIXED | usage.py 支持 data.usage 优先 + stream 终帧；(turn, step, attempt-id) 身份去重、两遍扫描顺序无关、缺身份/冲突 fail-closed；tests/test_usage_attempt_events.py 10 项 fixture（构造契约样例，非 API 实测） |
| F2.3 离线证据与不变量 | FIXED | tests/test_reconcile_e2e.py 三样例（metered fail→retry success / local_rejected / unknown_cost）端到端对账全过；reconciliation.json 6 校验全过；CSV 哈希锁定测试通过 |
| 文档 | FIXED | docs/PHASE0_R1_2_FIX_REPORT.md（新增）、PHASE0_AUDIT.md §2.3、HARNESS_INTEGRATION.md 事件结构分「实测/契约」两档标注 |

## 验证命令与结果

- `.venv/Scripts/python.exe -m pytest tests/ -q` → **79 passed / 0 failed / 0 skipped**。
- `.venv/Scripts/python.exe benchmarks/cache_benchmark.py --dry-run --run-id dryrun-r12` → 100/100 fake ok（离线、无密钥、无网络）。
- `.venv/Scripts/python.exe scripts/reconcile_live.py` → 总量与审计常数一致；6/6 校验通过。
- 未运行任何新 live 调用；无新增费用。

## 残留风险（如实声明）

1. assistant/attempt 真实故障事件分布未经 live 实测（本轮禁新增调用）；fixture 锁定解析语义而非上游频率。
2. 同一 step 内两个无 id attempt 用量恰好相等会被判重（当前无工具单步配置下不出现；已文档化）。
3. 实际扣费金额仍 unknown（余额分辨率/账单延迟）。
4. 存量 100 条任务有效性 unknown（响应未持久化；41 条 max-tokens 截断确定不完整）。

## 停止条件

停在 Phase 0。status.json 设为 READY_FOR_REVIEW，等待 GPT Planner 最终验收；未进入 Phase 1。
