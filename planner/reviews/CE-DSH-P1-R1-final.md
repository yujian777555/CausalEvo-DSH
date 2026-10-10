# CE-DSH-P1-R1 — Planner 最终验收与冻结（OFFLINE ONLY）

- 日期：2026-10-10
- 审查 GitHub main HEAD：c6276450fd97f0d1d047e151423bd5e2ecb21225
- Executor 主体提交：734aa16efa6f007ce4ee6ca5941a593e6792f8b2
- **结论：ACCEPTED / FROZEN / OFFLINE ONLY**
- 下一计划：CE-DSH-P1-R2（planner/latest_plan.md）
- Planner 读取提交源码、真实 GitHub 代码/测试/结果/文档；**未本地重跑 pytest，也未实测 Docker 或 API 账单**。下文清楚区分独立源码审查与 Executor 报告。

## I. P1-R1 Gates

| Gate | 决定 | 证据/限制 |
|---|---|---|
| P1-G1 | PASS | benchmarks/registry.json 及 26 个任务（13 train / 7 dev / 6 sealed_test）、代码和客观 Judge；明确本地任务只是工程 smoke |
| P1-G2 | PASS scoped offline | DockerExecutor 在代码中限定网络、rootfs、CPU/mem/pids/user/只读任务目录、timeout；7 项对抗性测试存在且 Executor 报告实跑通过；但 **Harness agent 本身尚未被真正边界隔离** |
| P1-G3 | PASS policy definition only | B0/B1 共享 Budget(2 provider calls, 2048 output tokens, 20 tool calls, 300s)，分别允许 1/2 attempts，无跨任务更新；运行时计费 Gate 尚未实现 |
| P1-G4 | PASS | 两份 manifest/report.json 各 26 requested/executed/scored、15 visible passes/0 sealed passes；noop fake model, 0/26 正确结果，不是模型性能 |
| P1-G5 | CONDITIONAL PASS | Executor 报告 123 passed 0 failed 0 skipped；相关测试文件可读；没有 Planner 本地测试重跑；主要配置与 split seed 固定 |
| P1-G6 | PASS | 历史 Phase 0 live/calls.csv Git blob SHA = 95d2fc112d37b4ad409190d3aba242276519613c，与冻结记录一致 |
| P1-G7 | PASS evidence-limited | repo 仅新增离线工件，Executor 报告零 live API；不能独立读取服务商账单 |
| P1-G8 | PASS remote | GitHub main HEAD = c627645...；local clean 仅 Executor 提供命令报告 |

## II. 验收的重要边界

1. **文件系统读取隔离未验证**：上游 DeepSeek-Harness `fs-sandbox` 官方文档说明其主要限制写入/编辑（workspace-write），reads pass through；不能因为 Shell/Web 被禁用或 Docker Judge 安全，就推断 Agent 文件读取被阻挡。src/causalevo/eval/executor.py 是 **judge subprocess** 沙箱，不是 DeepSeek-Harness 的 agent 工具层。Phase 1-R2 必须以 OS/独立运行世界或可证明的 per-read 访问控制实现 Agent workspace read confinement，包括 tool-fs 和 fs-search。
2. **LocalTrustedExecutor 只靠调用约束**：default_executor() 在无 Docker 时可降级 local-trusted。后续非可信模型产物执行路径必须程序级 fail-closed，禁止自动信任；CLI `--executor local` 只允许完全离线可信 fixture，无 key、无用户产生代码。
3. **公开的 sealed/reference 文件不是论文真正秘密测试**：26 个任务连同 sealed tests、reference patches 已公开提交到同一 GitHub 仓库。当前唯一可证明的是运行时 agent-visible workspace 不包含它们；将来不可用这些公开题作为未泄漏且未见过的论文最终评测数据。
4. **B0/B1 尚非真实 Agent baseline**：src/causalevo/eval/pipeline.py 使用 FakeAgent，`api_response_observed=True` 也是模拟语义。B0/B1 预算仅静态字段相同，没有真实 API calls/tokens/tools runtime 预算拒绝。
5. **未验证外部 Benchmark**：SWE-bench Verified 只是候选，未下载/运行。官方流程用 Docker 镜像与测试；不能将元数据审计当成已具备实际评估吞吐。实施前需冻结上游版本与相应 license。
6. **遗留 Phase 0 request 身份歧义**：同 turn/step、无 attempt id、计量恰好相同的事件在未知身份时可能误判重复；进入 live retries/multistep 前必须 fail-closed。
7. **镜像可复现**：DockerExecutor 当前默认 `python:3.11-slim` tag 而非 digest pinned；外部真实评估需固定镜像 digest。

本轮 Phase 1-R1 范围仅涵盖离线工程与 fake/replay 测试，上述未交付的真实模型桥接属于下一阶段，不是本轮失败项。

## III. 冻结信息

- 26 microtask、registry split seed=20261010、B0/B1 offline reports 保留；后续新增 run_id，不能覆盖原报告。
- P1-R1 完成状态 ACCEPTED / FROZEN / OFFLINE ONLY，不表示模型成功率可发表。
- phase0/live/calls.csv 一字节不改。
- Planner 正式批准进入 Phase 1-R2 离线 live-readiness bridge，**不批准任何新的 DeepSeek API 调用或费用**。
