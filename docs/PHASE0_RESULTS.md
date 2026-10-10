# Phase 0 结果（离线 vs 真实 API 严格分离）

日期：2026-10-10。计划：CE-DSH-P0-R1。本文只报告测量值，不做任何因果/进化效果结论。

## 1. 离线结果（dry-run，零费用，无密钥）

- 测试套件：`.venv/Scripts/python.exe -m pytest tests/ -q` → **42 passed, 0 failed, 0 skipped**（2026-10-10，Windows 原生 Python 3.10.1）。含失败注入：缺 usage fail-closed 停机、重试计量、预算拒绝、脱敏、工具禁用回归守卫。
- 端到端 dry-run：`benchmarks/cache_benchmark.py --dry-run --run-id dryrun002`，100/100 fake 调用成功，证据在 `results/phase0/dry-run/`（summary.json / calls.csv / preflight.json / config_snapshot.json）。FakeRunner 的数字不是真实缓存证据。

## 2. 真实 API 结果（live，run_id=p0live02）

### 2.1 运行条件

- 时间：2026-10-10（周六，全程 off-peak；calls.csv 逐次 UTC 时间戳）。
- 配置哈希 `a4f11755ea27380c`：model=`deepseek-flash`（wire id 实测，= DeepSeek-V4.1-Flash）、reasoningEffort=`low`、maxTokens=64、串行、无工具 profile（configs/dsh_bench_patch.yml）、交错顺序 A,B,C,D 循环。
- 运行时：deepseek-harness-sdk 0.1.5rc1 + runtime-bin 0.1.5rc1（win_amd64），隔离 DSH_HOME/workspace。
- 执行：100/100 成功，0 失败，0 重试，无 budget/fail-closed 中止。

### 2.2 缓存命中率（cache_read / total_prompt，逐次证据在 results/phase0/live/calls.csv）

| 组 | n | 命中率 mean (min–max) | cache_read tokens | 说明 |
|---|---|---|---|---|
| A 连续 Session | 25 | **0.748**（0.511–0.873） | 16,384 | 随历史增长从 256→896 tokens，128-token 粒度阶梯上升；历史长度混杂已标注 |
| B 同前缀跨 Session | 25 | **0.546**（恒定） | 6,400 | 每次恰好 256 tokens 命中（2×128 粒度），跨 session 前缀复用成立 |
| C 同前缀+变后缀 | 25 | **0.546**（恒定） | 6,400 | 与 B 完全一致：等长后缀变化不破坏前缀缓存 |
| D 变靠前前缀 | 25 | **0.000**（恒定） | 0 | 前缀第 2 行 4 字节变化使缓存全部失效 |

补充观察：A 组第 1 次调用即命中 256 tokens——与先前冒烟/调试调用共享系统提示词前缀，说明缓存可跨独立进程/session 复用。

### 2.3 Token 与费用

- 总 prompt tokens：45,500（uncached 27,316 + cache_read 22,784 + cache_write 0；上游未上报 cacheWriteTokens，按缺失桶披露）。
- 总 output tokens：3,833（含 reasoning）。
- 估算费用（USD→CNY 7.10 假设）：分时（off-peak）**¥0.0460**；峰值口径上界 **¥0.0921**。
- 平台对账：`/user/balance` 运行前 4.83 → 运行后 4.83 CNY；差值 0.00，低于余额显示分辨率（0.01 CNY）或存在账单延迟——以估算值为准并披露该限制。
- 另：开发期冒烟 1 次 + 首次崩溃运行 1 次，共 2 次额外表外调用（合计约 ¥0.001 估算），已如实披露。
- 预算：授权上限 ¥10；实际有效上限收紧至余额 ¥4.83；实际消耗 ≪ 上限。

### 2.4 安全与隔离验证（G3/G4 证据）

- 组合配置：`dsh --profile sdk --patch configs/dsh_bench_patch.yml --dump-config` 显示 50+ 工具/沙箱/上传插件 `disabled: true`；`tests/test_tool_disable.py` 回归守卫。
- live 全部 100 次调用：无任何 tool 事件、无子代理、无网络工具；模型单步直接作答（events 类型仅 agent/inbox、turn、step、system/user/assistant message、request/header、request/context）。
- 上传通道 session-telemetry-otel、session-log-deepseek 已禁用。
- API Key 仅从环境读取；`test_no_key_material_in_any_output` 验证产物无密钥；calls.csv 只含脱敏 session id 哈希。

## 3. 混杂与限制

1. A 组命中率趋势与历史长度增长混杂，不能与 B–D 直接等长比较。
2. D 组测的是前缀字节敏感性，不是 API `in-history` system-prompt-update 功能（该能力存在但未被本基准验证）。
3. 全部调用集中于同一约 70 秒窗口；交错分组降低但未消除时间漂移风险。
4. 缓存命中由服务端决定，128-token 粒度为观察推断，非官方承诺。
5. 余额对账分辨率有限；成本数字为基于官方价格页（2026-10-10）的估算，peak 口径为上界。

## 4. 可提交证据清单

- `results/phase0/live/{summary.json, calls.csv, preflight.json, config_snapshot.json}`（脱敏；dsh_home/ 与 workspace/ 不提交）
- `results/phase0/dry-run/` 同构离线证据
- `tests/`（42 项）、`docs/HARNESS_INTEGRATION.md`、`docs/PHASE0_AUDIT.md`
