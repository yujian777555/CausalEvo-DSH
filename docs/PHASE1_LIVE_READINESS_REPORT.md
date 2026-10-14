# Phase 1.5 Live Readiness Report（G5）

日期：2026-10-14。计划：CE-DSH-P1.5。本报告结论基于当日真实测试与运行证据；live 预算 = 0，本轮零 API 调用。

## 总体判断：**NOT READY**（用于真实外部基准 pilot）

分项全部通过的维度已具备 microtask 级 live pilot 的工程条件，但外部基准可用性未验证——按 Gate 规则（任一失败即 NOT READY），总体保持 NOT READY。

## 分项判定

| 维度 | 状态 | 依据 |
|---|---|---|
| Docker security | ✅ READY | Container Security Profile v2（read-only rootfs、tmpfs、cap-drop ALL、no-new-privileges、internal network）；tests/test_container_security_v2.py 9 项 + test_agent_fs_isolation.py 8 项实测通过；宿主读穿透（2026-10-10 实证）已被容器世界封堵 |
| Provider guard | ✅ READY | live 双条件授权门（`DEEPSEEK_API_KEY` + `CE_DSH_LIVE_AUTH=phase1-pilot`），任何网络访问前拒绝；tests/test_live_guard.py 10 项通过；测试中静态保证不触达 api.deepseek.com |
| Budget accounting | ✅ READY | RuntimeBudget 五维实时门控（预留/结算/超停）；unknown spend fail-closed；seq 身份判重（RISK-1 关闭）；tests/test_runtime_budget.py 10 项 |
| Trace completeness | ✅ READY | provider_kind/model_invoked/8 态/ledger/events_slim/manifest provenance 冻结并有 tests/test_protocol_freeze.py 10 项锁定 |
| Benchmark availability | ❌ NOT READY | SWE-bench Verified 数据/镜像未下载未实测；2026-10-13 本机无法访问 HF datasets-server；候选实例 id 仅来自文献；26 个 microtask 的 sealed 已公开于 GitHub，不构成论文未见 holdout |
| 宿主依赖 | ⚠️ 注意 | Docker Desktop 守护进程在本机会话间出现过停止/抖动；live pilot 前须确认 daemon 常驻 |

## 距 READY 的差距（进入付费 pilot 前的硬条件）

1. 外部基准可运行性实跑验证（≥1 个 SWE-bench Verified 实例在本机 Docker 完整跑通 oracle 流程），需要用户批准镜像/数据下载与小额 API 预算。
2. 独立私有 holdout 的存储与审查门槛（公开 microtask sealed 不构成）。
3. 用户对新 live 预算的明确授权（Phase 0 的 ¥10 不沿用）。
4. Docker daemon 常驻策略。

## 已就绪（可立即用于论文工程的部分）

- 容器化 agent 执行世界 + fake/replay 离线链路 + 独立 judge + 预算门控 + 可审计轨迹。
- B0/B1 协议与统计计划冻结（docs/PHASE1_EXPERIMENT_PROTOCOL.md、docs/PHASE1_STATISTICAL_PLAN.md）。

## 证据

- results/phase1/p15/{manifest.json, security_report.json, protocol_check.json}
- 测试套件全量结果见 planner/executor_report.md 与 status.json。
