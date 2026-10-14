# Executor Report — Phase 2.3 Counterfactual Intervention Foundation（CE-DSH-P2.3）

日期：2026-10-14。Executor：Kimi。本轮零 DeepSeek API 调用、零费用；冻结区（Phase 0/1/1.6/2.1/2.2）未触碰。

## 交付项

| 项 | 状态 | 证据 |
|---|---|---|
| S1 Intervention Schema | PASS | src/causalevo/intervention/schema.py（intervention_id/target_failure/type/description/required_change/expected_effect/confidence/tape_transform；可序列化、可校验） |
| S2 规则生成器 | PASS | generator.py：7 类失败全覆盖映射，unknown→no-op，弃判不干预；无 LLM |
| S3 反事实重放引擎 | PASS | src/causalevo/counterfactual/replay.py：确定性磁带变换（纯函数、原磁带不改）+ 容器世界真实重跑 + 独立 judge；3 案例（tool/verification/无效对照）实测 |
| S4 四臂基线 | PASS | B0 identity / B1 随机（seed 固定）/ B2 规则 / B3 诊断引导；同包络配对 |
| S5 评估协议 | PASS | docs/PHASE2_INTERVENTION_EVAL.md（outcome/efficiency/reliability/causal 指标，配对纪律，反虚假因果条款） |
| S6 反虚假因果 | PASS | 对照案例（错配干预无改善）、changed_steps 记录、B1 随机对照、诚实声明入 manifest |
| S7 结果产物 | PASS | results/phase2/intervention/ 四件（manifest/results/comparison/samples） |
| 测试 | PASS | **300 passed / 0 failed / 0 skipped**（261 + 39 新增：schema 15、磁带变换 11、反事实 7+产物/对照 6） |
| 文档 | PASS | docs/PHASE2_INTERVENTION_DESIGN.md、PHASE2_INTERVENTION_RESULTS.md |

## 实测数字（模拟机制，非真实模型证据）

B0 0/6 改善（恒零 ✓）；B1 随机 2/6；B2 规则 4/6；B3 诊断引导 4/6；对照案例 0 改善 ✓。

## 事故与修复

- 初跑 KeyError（新场景缺 ground-truth 映射）→ 补齐 SCENARIO_GROUND_TRUTH。
- Windows 目录名禁冒号 → case_id 改用 `--` 分隔。
- 控制案例初版被 B3 正确诊断"修复"（干预失配设计被诊断臂绕过）→ 对照案例改为强制错配干预。
- 成本断言初版假设干预必增费用 → 实测同调用数零增量，改为钉住该正确性质。

## 停止

停在 Phase 2.3。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。未宣称 Agent 自进化成功。
