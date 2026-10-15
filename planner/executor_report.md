# Executor Report — Phase 4 Real Agent Evolution Validation（CE-DSH-P4）

日期：2026-10-15。Executor：Kimi。冻结历史结果未触碰。**本轮发生了真实 DeepSeek API 调用（已授权、已记录、已计费），如实报告。**

## 交付项

| 项 | 状态 | 证据 |
|---|---|---|
| P4.1 协议冻结 | PASS | docs/PHASE4_EXPERIMENT_PROTOCOL.md（live 前冻结；含 2026-10-15 口径澄清修订章节） |
| P4.2 六臂基线 | PASS | src/causalevo/eval/live_pilot.py：B0/B1/B2/B3/B4/B5 + 冻结干预指令库 |
| P4.3 真实评估（小规模 pilot） | PASS | 26 任务 × 6 臂 × 2 种子 = 312 run；results/phase4/live/phase4-live-20261014T110259Z/ |
| P4.4 指标 | PASS | pass rate / recovery rate / evolution gain / 成本 / 步骤 |
| P4.5 因果验证 | PASS | B5 vs B1 随机干预对照；消融映射（A1–A4 到 B2/B4 口径） |
| P4.6 成本控制 | PASS | 预算上限 ¥3.00，实际 ¥0.715，逐臂 token/调用/费用记录；无 unknown_cost |
| P4.7 API 规则 | PASS | 双授权门 + dry-run 先行 + 全量调用记录 |
| P4.8 结果结构 | PASS | results/phase4/{live,dry-run(scratch)}：protocol.json、manifest.json、tasks.jsonl、baseline_results/statistical_tests/cost_analysis |
| P4.9 统计 | PASS | McNemar exact + paired bootstrap 95% CI（不报裸均值） |
| P4.10 论文证据报告 | PASS | docs/PHASE4_FINAL_EVALUATION.md（含负面/中性结果如实陈述） |
| 测试 | PASS | **409 passed / 0 failed / 0 skipped**（377 + 32 新增） |

## 结果（如实，含中性/负面）

pass rate：B0 0.808、B1 0.923、B2 0.885、B3 0.827、B4 0.846、B5 0.885。
**B5 vs B0：+7.7pp 但不显著（McNemar p=0.34，CI [-0.04,+0.19]）；B5 vs B1 随机：无优势（p=0.73，CI [-0.15,+0.06]）。**
RQ3 答案：本规模未能证明因果演化增益；随机干预数值最高。平台端到端成立，算法优越性未证实 —— 需要更难基准。

## 事故与修复

- analyze_phase4.py  docstring 残留引号语法错误 → 修复。
- provider_calls 断言误用包络口径（LLM 请求 vs agent attempt）→ 协议补口径澄清章节（不改指标），测试改为钉住真实语义。
- Docker daemon 会话间多次停止/WSL 后端 500 → 重启恢复；相关 flake 已记录。

## API 使用

- 312 次任务 run（每 run 2–8 次 LLM 请求），总 ¥0.715；授权：用户 Phase 4 批准 + CE_DSH_LIVE_AUTH 门；全部记录在 results/phase4/live/。

## 停止

停在 Phase 4。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。
