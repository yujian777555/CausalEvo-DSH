# Executor Report — CE-DSH-P4-R1.1（Phase 4 证据与算法保真修复）

日期：2026-10-14。Executor：Kimi。**本轮新增真实 API 调用 0 次、新增费用 ¥0。** 冻结数据（Phase 0–3、Phase 4 原始 312 行）未修改。

## Gate 结果

| Gate | 状态 | 证据 |
|---|---|---|
| A 证据可复算 | PASS | tasks.jsonl 本地存在（SHA-256 `21dd5dc0…13bcbc`）；auditable_tasks.jsonl（schema v1 + 行哈希）已提交；scripts/reconcile_phase4_rows.py 从表重算全部指标与已提交分析逐项相等（实测） |
| B 算法保真 | PASS | docs/PHASE4_ALGORITHM_FIDELITY_AUDIT.md 逐臂追踪；B4=heuristic proxy、B5=静态 bundle 如实披露；新 `CausalPolicyAdapter`（adapter_version r1.1）真实调用 LinUCB controller / 真实读取冻结 Pareto 前沿并校验 genome id + 文件 SHA；9 项测试 |
| C 逐请求预算门 | PASS | src/causalevo/eval/budget_proxy.py：发送前 授权+去重+配额+最坏预留；usage 原子结算（FIFO 释放预留，疑似计费不释放）；fail-closed 停止且 ledger 逐事件落盘；tests/test_budget_proxy.py 10 项（cap 第 4 请求上游零调用、500/缺 usage/断流停机、直连证明等） |
| D 统计 | PASS | legacy_iid_paired 原样保留 + 新 task_id cluster bootstrap（B5 vs B1 CI [-0.135,+0.058] 跨 0，负面结论不变）+ task-level sensitivity + retry 频率；写入 versioned statistical_tests_r1_1.json |
| E 无泄漏/冻结完整 | PASS | 无 sk-/路径/holdout 内容入产物；Phase0–3 哈希不变；436 测试全绿 |
| F 零新调用 | PASS | 本轮 API 调用 0、费用 ¥0 |
| G 远端一致 | PASS | 见提交记录 |

## P0 Bug 修复位置

- Bug1（unknown_cost 仍重试）：live_pilot.py `run_task_arm` — _STOP_KINDS（unknown_cost/budget_stop/transport/protocol）不再重试并记录 abort_reason；runner 层全局停止。
- Bug2（异常退出误报 none）：harness_agent.py — 无 final 消息按 rc 区分 transport/protocol，绝不默认 none。
- Bug3（状态混淆）：live_pilot.py — attempt_1_status / attempt_2_status / final_status / abort_reason / per-attempt provider_requests / actual_agent_attempts 全字段分离。
- Bug4（预留泄漏）：runtime_budget.py — 逐请求预留 FIFO，结算原子转换，疑似计费不释放，unknown_cost 不继续。

## Genome/Phenotype 审计（S4）

144 基因型 → 16 唯一表型（重复率 88.9%）；退化基因 reflection_step/retry_strategy（标 reserved）；verification_level 1=2。详见 docs/PHASE4_GENOME_PHENOTYPE_AUDIT.md。冻结 3.2 代码未改。

## DeepSeek Direct Connection Audit

见 docs/PHASE4_R1_1_AUDIT_ADDENDUM.md §4：宿主与容器客户端均显式空 ProxyHandler 直连；容器 scrub 代理环境 + NO_PROXY 钉住；TUN 模式无法配置级证明 → 标记 `DIRECT_ROUTE_UNVERIFIED`；本轮零 live 调用故无路由级实测。GitHub 等其他流量代理不受影响。

## 测试

**436 passed / 0 failed / 0 skipped**（409 + 27 新增：budget_proxy 10、adapter 9、direct_connect 5、reservation 3 等）。

## 未解决风险

1. TUN 级直连未证（DIRECT_ROUTE_UNVERIFIED）。
2. 新 adapter 只有离线行为证据；真实 CEA pilot 需新预算授权（预注册草案 docs/PHASE4_NEXT_PILOT_PREREG.md）。
3. Docker daemon 会话间稳定性（运维项）。

## 停止

停在 Phase 4 R1.1。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。未进入 Phase 5。
