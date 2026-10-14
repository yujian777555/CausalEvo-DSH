# Executor Report — Phase 1.5 Live Readiness Gate（CE-DSH-P1.5）

日期：2026-10-14。Executor：Kimi。本轮完全离线，**live API 调用 0 次、费用 ¥0**；Phase 0 / Phase 1 R1 / R2 冻结数据未触碰。

## 总览

- 测试：**193 passed / 0 failed / 0 skipped**（164 回归 + 29 新增：live_guard 10、protocol_freeze 10、container_security_v2 9）。
- 安全专项电池（p15 gate）：41 passed，protocol checks 全过，artifacts 在 results/phase1/p15/。
-  readiness 结论：**NOT READY**（唯一失败维度：外部基准可用性未验证；详见 docs/PHASE1_LIVE_READINESS_REPORT.md）。

## Gate 逐项

| Gate | 状态 | 证据 |
|---|---|---|
| G1 容器加固 v2 | PASS | --read-only rootfs、tmpfs /tmp(noexec)+.cache、cap-drop ALL、no-new-privileges、internal network ceval-net + provider 容器（唯一可达端点）；9 项 v2 测试 + 8 项 FS 越界回归实测通过；含 capability/metadata-service/ symlink 用例 |
| G2 Provider 适配 + 授权门 | PASS | eval/provider.py：fake/live 同形 ProviderEndpoint；live_enabled 默认 False；无双凭证→拒绝；tests/test_live_guard.py 10 项（含 socket 拦截证明构造期零网络、CLI 退出码 2） |
| G3 实验协议冻结 | PASS | docs/PHASE1_EXPERIMENT_PROTOCOL.md（B0/B1、预算包络、三轴指标、judge 盲化、trace 模式、修订规则，冻结 2026-10-13） |
| G4 统计计划 | PASS | docs/PHASE1_STATISTICAL_PLAN.md（paired tasks、固定 seed 列表、McNemar exact + Clopper-Pearson + Wilson + paired bootstrap、反钓鱼条款、功效说明） |
| G5 Readiness 报告 | PASS | docs/PHASE1_LIVE_READINESS_REPORT.md，结论 NOT READY（外部基准维度） |
| 测试数 | PASS（29 ≥ 15） | 见上 |
| p15 artifacts | PASS | manifest.json / security_report.json / protocol_check.json，由 scripts/run_p15_gate.py 真实运行生成 |

## 事故与修复记录

1. 硬化容器初版启动失败：runtime 插件加载器需在 $HOME/.cache 解包并 mmap 原生 sidecar（koffi/rg），read-only rootfs + nosuid tmpfs 阻断 → 增加专用 `.cache` exec tmpfs（/tmp 保持 noexec），最小权限定位经三个变体实验确定。
2. 磁带 provider 长度不足曾使 provider_error 场景第 5 次重试落入"done"兜底并被计费一次 → tape 覆盖加长（+10 margin）并在 scenario_tape 文档中记录重试地平线约束。
3. Docker Desktop 守护进程两次在会话间停止 → 测试跳过/失败为环境抖动，重启后全绿；已列入 readiness 注意项。

## 残留风险

- 外部基准（SWE-bench Verified）未下载未运行，HF 元数据本机不可达（NOT_VERIFIED）。
- 26 个 microtask sealed 已公开，不是论文 holdout。
- Docker daemon 常驻需 live 前确认。

## 停止

停在 Phase 1.5。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。未进入 Phase 2，未申请预算。
