# Phase 0 R1.2 计量闭环修复报告（Executor 侧）

日期：2026-10-10。计划：CE-DSH-P0-R1.2（来源 planner/reviews/CE-DSH-P0-R1.1-review.md）。
硬约束遵守：原始 `results/phase0/live/calls.csv` 未改（SHA-256 `1961bdd8…e364c59`，测试锁定）；**零新增 live API 调用**；全部修复与验证离线完成。代码修复不等于新的 API 实测。

## F2.1 多次 attempt 的 Token 桶完整累计（P0）

- 根因：`_row()` 的费用与 output_tokens_all_attempts 累计了所有 attempts，但输入桶/总 prompt/命中率只取最后一次 attempt。
- 修复（`src/causalevo/benchmark.py::_row`）：
  - 新增全 attempt 计费列：`uncached_input_tokens_all_attempts`、`cache_read_tokens_all_attempts`、`cache_write_tokens_all_attempts`、`cache_write_reported_all_attempts`、`total_prompt_tokens_all_attempts`、`cache_hit_rate_all_attempts`（由求和桶加权）；保留 `final_attempt_usage`（JSON 字符串）与 legacy 最终 attempt 列，语义分列注释，不允许冒充总账。
  - `cache_write_reported_all_attempts` 仅当**所有**已计量 attempt 均上报时为 true；未上报保持缺失，不伪造 0。
  - `aggregate_rows()` 一律使用 all-attempts 列（旧 CSV 回退 legacy 列：100 行均为 1 attempt，等价无损）。
  - overall 新增 `unknown_spend_attempts` 与 `cost_completeness`（complete / partial_unknown），并显式标注 `known_measured_cost_cny_*`：已知费用不再被描述为完整成本。
- 一致性断言：`reconcile.py` 新增 `all_attempts_buckets_cover_final_attempt` 检查；`tests/test_reconcile_e2e.py` 做离线 CSV 端到端对账（metered fail→retry success / local_rejected / unknown_cost 三样例全过）。

## F2.2 assistant/attempt 的 settled usage 解析（P0）

- 根因：`_usage_from_message_event` 仅接受 assistant/message，失败/重试的 assistant/attempt 用量被当作缺失。
- 修复（`src/causalevo/usage.py`）：
  - `assistant/attempt` 事件支持 `data.usage`（优先，上游契约的权威位置）与 `data.stream` 最终 `chunk:usage` 帧；分帧不累计。
  - 身份去重：message 按 (turn, step)，attempt 按 (turn, step, attempt-id)；无 id 的 attempt 仅在与该 step 已提交 message 用量相等时判重；用量不同即为独立计费请求（如 provider 重试）。两遍扫描保证顺序无关。
  - 缺 turn/step 身份或同一身份用量冲突 → UsageUnavailable（fail-closed），禁止盲目加总。
  - 带可靠 usage 的失败 attempt 必须计费，不再触发停机；无 usage 且不能证实未发出的失败仍 unknown_cost 停机（F2 语义保留）。
- 新测试 `tests/test_usage_attempt_events.py`：10 项 fixture（attempt-only 失败计费、stream 终帧、与 message 等量去重、不同量独立计费、重复事件去重、冲突用量 fail-closed、缺身份 fail-closed、顺序无关性等）。
- 注意：这些 fixture 是按上游事件结构契约**构造**的离线样例，不是真实 API 故障的抓包证据（已在 HARNESS_INTEGRATION.md 标注）。

## 不变量核验

- 原始 100 条 CSV 哈希不变；历史数字保持 27316 / 29184 / 56500 / 3833 / 0.5165309734513275 / ¥0.0460417392（reconcile 重跑确认）。
- `actual_billed_cost_cny` 继续为 null；存量 task_valid=unknown；41 条 max-tokens 披露保留。

## 验证证据

- `pytest tests/ -q` → **79 passed / 0 failed / 0 skipped**（R1.2 后实际重跑）。
- `--dry-run --run-id dryrun-r12` → 100/100 fake ok，离线无密钥。
- `results/phase0/live/reconciliation.json` 重新生成，6 项校验全过（含新增 all-attempts 覆盖检查）。

## 残留风险

- assistant/attempt 的真实故障事件分布未经 live 实测（本轮禁止新增调用）；契约 fixture 覆盖了解析语义，不覆盖上游行为频率。
- 极端情形：同一 step 内两个无 id attempt 用量恰好相等会被判重（少计一次）；该情形在当前无工具基准配置（每 turn 单步、retry 由外层 SDK 异常路径报告）下不会出现；如未来启用工具/多步，需以上游 attempt id 为准。
