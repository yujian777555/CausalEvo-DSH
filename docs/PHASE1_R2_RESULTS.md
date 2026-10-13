# Phase 1 R2 结果（全部离线，零 API 费用）

日期：2026-10-13。计划：CE-DSH-P1-R2。本轮无任何真实模型网络请求；fake provider 走协议层（127.0.0.1），usage 数字为合成值，仅验证计量链路，不是计费/性能证据。

## 1. 测试

- 命令：`.venv/Scripts/python.exe -m pytest tests/ -q` → **164 passed / 0 failed / 0 skipped**（含 Docker 对抗性与容器 e2e，真实容器执行）。
- 其中本轮新增 41 项：runtime_budget(10)、fake_provider(8)、agent_fs_isolation(8)、agent_bridge_e2e(8)、executor_guard(7)。
- 修复记录：`test_two_metered_failures_both_bill` 原断言硬编码 off-peak 价格，属日历相关测试 bug（2026-10-13 为周二峰时窗口触发），已改为按行内记录的 price_tier 计算期望值。

## 2. S0 安全门（最高优先级）：结论与实测证据

- **宿主 runtime 读穿透实测确认**：scripts/probe_fs_escape.py —— task profile 下 agent `read` 工具把宿主 canary（`HOST_SECRET_CANARY_7f3a9c`）完整读出（fs-sandbox 的 workspace-write 只限写）。→ 宿主 runtime 不是隔离边界。
- **容器世界修复并实测通过**：整个 DSH runtime 运行在一次性容器（镜像 `causalevo-dsh-agent:0.1.0`，digest 钉死基座 `python@sha256:e88e9763…`，vendored wheels + SHA256SUMS），只挂载每任务 workspace 到 /work。8 类对抗性测试（tests/test_agent_fs_isolation.py）全过：绝对路径/穿越/符号链接/其他任务目录/宿主密钥/glob/grep 全部无法读取 canary；/etc 写入被拒；workspace 内写入正常（正对照）。
- LocalTrustedExecutor 改为程序级守卫：直接构造抛 RuntimeError，必须 `for_trusted_content()`；`default_executor(for_untrusted=True)` 无 Docker 时 fail-closed 抛 ExecutorUnavailable。
- S0-Gate：**通过**（仅在容器世界；宿主直跑被永久标记为 probe/debug 用途）。

## 3. S1 Harness 桥接（真实 runtime + fake provider 协议层）

- FakeProvider 只绑定 127.0.0.1，讲 OpenAI 兼容 SSE（实测 wire format 见 docs/PHASE1_R2_HARNESS_BRIDGE.md §2：usage 映射 prompt_cache_hit/miss→cacheRead/inputTokens；工具 read/write/edit/glob/grep；write 前必须先 read）。
- 容器内真实 SDK/runtime 经 host.docker.internal 连 fake provider，完整经过 agent 循环、工具分发、session 事件——非 SDK 内部 mock。
- 端到端闭环 agent→tools→workspace→judge→trace 实测：correct_fix 3/3、noop 0/26（诚实）、wrong_fix 0/3（invalid=0，区分为测试失败）、bad_tool_call 0/3（unknown tool 被运行时正常回报）、provider_error fail-closed（1 任务后停机）、tool_over_budget budget_stop。
- 证据目录：`results/phase1/r2-offline/<run_id>/{manifest.json, traces.jsonl, report.json}`，manifest 含 repo SHA/SDK 版本/镜像 digest/配置哈希（provenance_block）。

## 4. S2 运行时预算门控

- `RuntimeBudget`：发送前预留、收到 settled usage 后按真实桶结算；provider 调用/工具调用/输出 token/费用/墙钟五维上限；超限即 docker kill 硬停（事件流反应式）。
- B0/B1 共用同一 envelope（2 calls / 2048 out tokens / 20 tool calls / 300s），B1 的反思从同一额度扣除；平价有测试。
- 未知计费 fail-closed：无 settled usage 的 attempt 记 unknown_spend_attempts 并停止后续任务（agent-11 上报的 provider_error 漏计已修复并加测试锁定）。
- RISK-1 落地：usage 值永不用于判重；attempt 事件按 seq 作请求身份（实测 6 事件↔6 HTTP 请求 1:1）；无 id 等量歧义 → fail-closed。

## 5. S3 轨迹与隔离

- TaskTrace 新增 provider_kind/model_invoked；api_response_observed 仅 live 才为真。events_slim 只含结构+哈希，不含正文。
- sealed/reference 不进入容器挂载；judge 侧独立容器注入。26 个 microtask 的 sealed 已公开在 GitHub —— 明确声明不能作为论文未见 holdout。

## 6. S4 SWE-bench 可行性

- 见 docs/PHASE1_R2_PILOT_DESIGN.md：可行性核对表（多项 NOT_VERIFIED，含 2026-10-13 本机无法访问 HF datasets-server）、pilot 候选实例（文献来源，未实测）、等成本 B0/B1 矩阵、预算估算（全部标注为假设估算）、floor-effect 防护。未发送任何真实请求。

## 7. 费用

- 本轮 live API 调用 **0 次**，新增费用 **¥0**。`--live` 在无 `CE_DSH_LIVE_AUTH=phase1-pilot` 时于任何网络访问前拒绝（测试锁定）。

## 8. 残留风险

1. 容器网络为 bridge（fake 需要到达宿主）；live 前需收紧 egress 至 api.deepseek.com（已列入 live 前置条件）。
2. 容器内 rootfs 非只读（agent 用户非 root；/etc 写入被 workspace-write 拦）；如需更强可再加 --read-only + tmpfs。
3. 预算的容器内 mid-run 执行为事件流反应式（收到事件即停），跨请求预留为保守上界；单请求内部的瞬时超额无法先于其完成被发现。
4. HostHarnessRunner 仍存在（probe 用途，文档已标注禁止用于任务执行）。
