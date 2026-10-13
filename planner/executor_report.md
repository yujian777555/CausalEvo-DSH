# Executor Report — Plan CE-DSH-P1-R2（Phase 1 R2：安全边界 + Harness 桥接 + 运行时预算）

日期：2026-10-13。Executor：Kimi。本轮完全离线，**零新增 live API 调用、零费用**；Phase 0/Phase1-R1 历史数据未触碰。
（历史轮次报告见 git 历史。）

## 总览

- S0–S4 全部交付；测试 **164 passed / 0 failed / 0 skipped**（123 回归 + 41 新增，全部真实运行，含真实容器的对抗性与 e2e 测试）。
- S0-Gate：**通过（容器世界）**。宿主 runtime 读穿透已实测确认并判定不可用于任务执行；容器世界 8 类越界测试全过。
- 无任何模型性能宣称；fake provider 数字为合成计量链路验证。

## 计划项状态

| 项 | 状态 | 证据 |
|---|---|---|
| S0 FS 读取隔离 | PASS | docs/PHASE1_R2_SECURITY_MODEL.md；probe_fs_escape.py（宿主泄漏实证）/ probe_fs_escape_container.py（容器阻断实证）；tests/test_agent_fs_isolation.py 8 项实测 |
| S0 executor 守卫 | PASS | LocalTrustedExecutor 构造守卫 + default_executor for_untrusted fail-closed；tests/test_executor_guard.py 7 项 |
| S1 Harness 桥接 | PASS | fake_provider.py（协议层）、harness_agent.py（容器 runner）、agent_pipeline.py、scenarios.py（7 场景）；tests/test_agent_bridge_e2e.py 8 项；wire format 实测记录 |
| S2 运行时预算 | PASS | runtime_budget.py（预留/结算/五维上限/unknown fail-closed/墙钟 watchdog）；tests/test_runtime_budget.py 10 项；B0/B1 平价测试 |
| S2 身份判重（RISK-1） | PASS | seq 身份 + 等量歧义 fail-closed；tests/test_usage_attempt_events.py 12 项（含 6 等量事件全计费回归） |
| S3 轨迹/隔离 | PASS | provider_kind/model_invoked、events_slim、provenance_block（repo SHA/SDK/镜像 digest）；sealed 不进容器 |
| S4 SWE-bench 可行性 | PASS（方案级） | docs/PHASE1_R2_PILOT_DESIGN.md；HF 不可达标 NOT_VERIFIED；零真实请求 |
| live 授权门 | PASS | require_live_authorization 双条件拒绝，先于任何网络访问；`--live` 实测返回 2 |

## 验证命令（实际执行）

- `.venv/Scripts/python.exe -m pytest tests/ -q` → 164 passed（138s，含容器测试）
- `scripts/run_agent_task.py --fake --scenario noop`（B0、B1 各 26 任务，容器桥接）→ 各 26/26 executed，0 succeeded（诚实 noop）
- 场景证据 5 组（correct_fix 3/3、wrong_fix 0/3、bad_tool_call 0/3、provider_error fail-closed、tool_over_budget budget_stop）→ results/phase1/r2-offline/
- `docker build docker/dsh-agent` → 成功；镜像 digest 与 wheels SHA256SUMS 已记录

## 事故与修复

1. swarm 测试发现 provider_error 路径下 6 次已发送 HTTP 请求未被计量（无 usage 帧）→ 修复：未计量 attempt 记 unknown_spend_attempts + unknown_cost fail-closed 停机，测试锁定。
2. 测试日历 bug：硬编码 off-peak 断言在周二峰时窗口失败 → 改为按行内记录 tier 计算。
3. Dockerfile pip 在线安装被宿主网络/代理拦截 → 改为 vendored wheels 离线构建（更可复现）。

## 残留风险

见 docs/PHASE1_R2_RESULTS.md §8（bridge 网络、容器 rootfs、反应式 mid-run 预算、HostHarnessRunner 保留为 probe 用途）。

## 停止

停在 Phase 1 R2。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。未进入付费 pilot / Phase 2。
