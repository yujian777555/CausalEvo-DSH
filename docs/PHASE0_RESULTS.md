# Phase 0 结果（离线 vs 真实 API 严格分离）

日期：2026-10-10（R1.1 修正版）。计划：CE-DSH-P0-R1 → 修复 CE-DSH-P0-R1.1。本文只报告测量值，不做任何因果/进化效果结论。
所有总量数字由 `results/phase0/live/calls.csv`（SHA-256 `1961bdd8…e364c59`）经 `src/causalevo/reconcile.py` 无损重算生成，机器校验见 `results/phase0/live/reconciliation.json`（全部检查通过）。

## 1. 离线结果（dry-run，零费用，无密钥）

- 测试套件：`.venv/Scripts/python.exe -m pytest tests/ -q` → **64 passed, 0 failed, 0 skipped**（2026-10-10 R1.1 后，Windows 原生 Python 3.10.1）。含失败注入矩阵：缺 usage fail-closed 停机、无 usage 失败→unknown_cost 停机、带 usage 失败计费后重试、本地拒绝零成本继续、预算拒绝、脱敏精度、工具禁用回归、live CSV 一致性。
- 端到端 dry-run：`benchmarks/cache_benchmark.py --dry-run --run-id dryrun-r11`，100/100 fake 调用成功，证据在 `results/phase0/dry-run/`。FakeRunner 的数字不是真实缓存证据。

## 2. 真实 API 结果（live，run_id=p0live02，数据未重跑）

### 2.1 运行条件

- 时间：2026-10-10（周六，全程 off-peak；calls.csv 逐次 UTC 时间戳；四组交错执行，总时长约 70 秒）。
- 配置：legacy raw 配置哈希 `a4f11755ea27380c`；model=`deepseek-flash`（wire id 实测，= DeepSeek-V4.1-Flash）、reasoningEffort=`low`、maxTokens=64、串行、无工具 profile（configs/dsh_bench_patch.yml）。
- 运行时：deepseek-harness-sdk 0.1.5rc1 + runtime-bin 0.1.5rc1（win_amd64），隔离 DSH_HOME/workspace。
- 执行：100/100 次 API 观测获得完整 usage（0 失败、0 重试、0 unknown_cost）。

### 2.2 缓存命中率（逐次证据：results/phase0/live/calls.csv）

| 组 | n | 加权命中率 | 逐请求均值 | cache_read tokens | 说明 |
|---|---|---|---|---|---|
| A 连续 Session | 25 | 0.7683 | 0.7477 | 16,384 | 随历史增长 256→896 tokens，128-token 粒度阶梯；历史长度混杂已标注 |
| B 同前缀跨 Session | 25 | 0.5458 | 0.5458 | 6,400 | 每次恰好 256 tokens 命中（2×128 粒度），跨 session 前缀复用成立 |
| C 同前缀+变后缀 | 25 | 0.5458 | 0.5458 | 6,400 | 与 B 一致：等长后缀变化不破坏前缀缓存 |
| D 变靠前前缀 | 25 | 0.0000 | 0.0000 | 0 | 前缀第 2 行 4 字节变化使缓存全部失效 |

**整体（四组合计）**：weighted_cache_hit_rate = 29184/56500 = **0.5165**（token 加权）；mean_per_request = **0.4598**（逐请求比率平均）。两者不同：前者是字节级加权，后者把每次调用等权；报告两者以避免口径混淆。

### 2.3 Token 与费用

- prompt tokens 合计 **56,500** = uncached **27,316** + cache_read **29,184**（cache_write 上游未上报，按缺失桶披露）。
- output tokens 合计 **3,833**（含 reasoning；100 次调用各 1 attempt，无重试）。
- 估算费用（基于官方价格页 2026-10-10 与 USD→CNY 7.10 假设的**估算值**）：off-peak **¥0.0460417392**；峰值口径上界 **¥0.0920834784**。
- 平台余额对账：`/user/balance` 4.83 → 4.83 CNY，visible delta = 0。余额显示分辨率 0.01 CNY 且账单可能延迟——**实际扣费金额 unknown**，不得以差值 0 记作已核实账单。
- 开发期另有 2 次表外调用（冒烟 1 + 崩溃运行 1），估算 ≈ ¥0.001，已披露。
- 预算：授权上限 ¥10；运行时收紧至余额 ¥4.83；消耗远低于上限。

### 2.4 任务输出有效性（R1.1-F3 分层）

- response_accepted = 100/100（finish_reason 非空且 usage 完整可信的有效 API 观测）。
- **finish_reason 分布：completed 59 / max-tokens 41（A=25/0，B=12/13，C=15/10，D=7/18）**。max-tokens 表示输出在 64 token 处截断，不是完整任务输出。
- task_valid = **unknown ×100**：原始 CSV 未持久化响应正文，无法独立验证 JSON 正确性；不得从 completed 推断任务成功。新代码已改为只存 response 哈希 + 校验状态（不落原文）。

### 2.5 安全与隔离验证（G3/G4 证据）

- 组合配置 dump 显示 50+ 工具/沙箱/上传插件 `disabled: true`；`tests/test_tool_disable.py` 回归守卫。
- live 100 次调用无任何 tool 事件、无子代理、无网络工具；模型单步直接作答。
- 上传通道 session-telemetry-otel、session-log-deepseek 已禁用。
- API Key 仅从环境读取；产物脱敏测试通过；calls.csv 只含脱敏 session id 哈希。

## 3. 混杂与限制

1. A 组命中率趋势与历史长度增长混杂，不能与 B–D 直接等长比较。
2. D 组测的是前缀字节敏感性，不是 API `in-history` system-prompt-update 功能。
3. 100 次调用集中于约 70 秒窗口；交错分组降低但未消除时间漂移。
4. 128-token 缓存粒度为观察推断，非官方 API 契约。
5. 成本为基于价格页的估算值；实际扣费 unknown（余额分辨率/延迟限制）。
6. 41/100 次输出被 max-tokens 截断：缓存计量有效，任务输出完整性不成立。

## 4. 可提交证据清单

- `results/phase0/live/{calls.csv（原始，不可改）, summary.json（CSV 回填）, reconciliation.json, preflight.json, config_snapshot.json}`
- `results/phase0/dry-run/` 同构离线证据（R1.1 后重新生成）
- `tests/`（64 项）、`docs/HARNESS_INTEGRATION.md`、`docs/PHASE0_AUDIT.md`、`docs/PHASE0_R1_1_FIX_REPORT.md`
