# Phase 0 R1.1 定向修复报告（Executor 侧）

日期：2026-10-10。修复计划：CE-DSH-P0-R1.1（来源 planner/reviews/CE-DSH-P0-R1-review.md）。
原则：原始 `results/phase0/live/calls.csv` 一字节未改（SHA-256 `1961bdd81a7f6a4ad4169d6f246530ed3df3170f70948f85de13ca136e364c59`，测试锁定）；零新增 live API 调用；全部修复离线完成。

## F1 聚合与跨文件一致性（P0）

- 根因：旧报告的总体数字（45500/22784/0.5006）为手抄错误；组级数字正确但总体行算错。
- 修复：
  - `src/causalevo/benchmark.py` 新增 `aggregate_rows()`：overall 块含 logical_calls、completed_calls、provider_attempts、metered_attempts、unknown_spend_calls、response_accepted、task_valid_counts、四个 token 桶、total_prompt、weighted_cache_hit_rate、mean_per_request_cache_hit_rate、finish_reason 分布、双口径费用；summary 内置 groups==overall 一致性自检字段。
  - 新增 `src/causalevo/reconcile.py` + `scripts/reconcile_live.py`：从不可变 CSV 无损重算，生成 `results/phase0/live/reconciliation.json`（文件 SHA-256、计算规则、5 项校验全过）并回填 `summary.json`（标注 backfilled_from）。
- 纠正后权威数字（机器重算，与 Planner 独立审计一致）：uncached 27,316 / cache_read 29,184 / total_prompt 56,500 / output 3,833 / 加权命中率 0.51653 / 逐请求均值 0.45984 / off-peak 估算 ¥0.0460417392 / peak 上界 ¥0.0920834784。
- 新测试 `tests/test_live_csv_consistency.py`：7 项，把审计常数钉死在 CI（CSV 哈希、总量、finish 分布、组==总体、reconcile 校验、summary==CSV）。

## F2 失败/重试的未知计费 fail-closed（P0）

- 根因：旧 `_execute_call` 只在 outcome.ok 时解析 usage；无 usage 的失败以 0 成本继续。
- 修复（benchmark.py）：
  - 每次 attempt 无论成败都解析 events 取 usage；带 usage 的失败照常计费（metered error，可重试）。
  - 失败且无 usage：区分 `error_kind=="local_rejected"`（证实未发出，零成本可继续）与其他（transport/provider/未知）→ `unknown_cost`，立即停机，费用标未知而非 ¥0。
  - 成功但 usage 缺失 → `fail_closed` 停机（沿用并修正状态传播）。
  - gate 预检按「剩余调用 × (1+max_retries)」的 attempt 上界计价。
  - summary 区分 provider_attempts / logical_calls / completed_calls / metered_attempts / unknown_spend_calls / measured cost。
- 新测试 `tests/test_failure_metering.py`：5 项矩阵（无 usage 传输失败停机、带 usage 传输失败计费重试、HTTP 失败带 usage 计费、重试后成功双 attempt 计量、本地拒绝零成本继续）。原 FlakyRunner（无 usage 失败重试）测试已替换，不再被宣称为完整计费测试。

## F3 API 成功 ≠ 任务输出完整（P1）

- 修复：
  - row 新增 `response_accepted`（turn 完成且 usage 可信）与 `task_valid`（finish_reason=completed 且响应逐字节等于期望 minified JSON → valid；max-tokens/内容不符 → invalid；无响应可查 → unknown）及 `response_sha16`（只存哈希不存原文）。
  - `scenarios.expected_response(group, index)` 提供确定性期望值。
- 对存量 100 条的披露：CSV 无响应正文 → task_valid=unknown ×100；finish 分布 completed 59 / max-tokens 41（A=25/0、B=12/13、C=15/10、D=7/18）；不声称 100/100 JSON 正确。
- 新测试 `tests/test_task_validity.py`：4 项（精确 JSON valid、max-tokens invalid 但 response_accepted、错误 JSON invalid、completed 无响应 unknown）。

## F4 配置哈希/快照脱敏（P1）

- 根因：`_SENSITIVE_KEY_RE` 的宽泛 `token` 子串误伤 `max_tokens`、`prompt_overhead_tokens`；`config_hash` 只哈希原始 YAML。
- 修复：
  - `redaction.py`：改为明确凭据字段名白名单（api_key/authorization/secret/token/…），`max_tokens` 等数值字段不再脱敏。
  - `benchmark.py`：新增 `effective_config_fingerprint()`（model/effort/max_tokens/calls/interleave/retries/prompt_overhead + patch 文件 SHA-256 + SDK 版本）；CLI override 经 BenchConfig 字段生效故自动被覆盖；预算区分 authorized_cap_cny 与 runtime_cap_cny（余额收紧只改授权记录，不改实验指纹）。
  - legacy raw 哈希 `a4f11755ea27380c` 保留并标注定义；旧 config_snapshot.json 的过度脱敏字段在此披露为已知缺陷（不重写历史文件）。
- 新测试 `tests/test_config_fingerprint.py`：test_numeric_token_fields_are_preserved、test_secrets_are_redacted、test_cli_overrides_affect_effective_hash、test_patch_fingerprint_changes。

## F5 文档与状态一致性

- `docs/PHASE0_RESULTS.md`、`docs/PHASE0_AUDIT.md`、`planner/executor_report.md`、`status.json` 全部改用 reconcile 重算数字；费用统一标注为估算值；`actual_billed_cost_cny` 改为 `null`（unknown），保留 `visible_balance_delta_cny: 0`。
- 持续披露：四组约 70 秒集中窗口、A 组历史混杂、D≠in-history update、128-token 粒度为观察。

## 验证证据

- `pytest tests/ -q` → **64 passed / 0 failed / 0 skipped**（2026-10-10，R1.1 后实际重跑）。
- `--dry-run --run-id dryrun-r11` → 100/100 fake ok，无需密钥无需联网。
- `reconciliation.json` 5 项校验全过；CSV 哈希锁定。
- 未新增任何 live API 调用（本轮零费用）。

## 无法验证事项（如实声明）

- 实际扣费金额：平台余额分辨率 0.01 CNY + 可能延迟，无法确认，标记 unknown。
- 100 条存量的任务输出正确性：响应未持久化，task_valid 只能标 unknown。
- 工具禁用的 runtime 证据来自本机执行环境（Planner 环境未复跑）。
