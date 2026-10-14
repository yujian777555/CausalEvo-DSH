# Executor Report — Phase 3.2 Multi-objective Causal Intervention Evolution（CE-DSH-P3.2）

日期：2026-10-14。Executor：Kimi。本轮零 DeepSeek API 调用、零费用；冻结区（含 Phase 3.1）未触碰。

## 交付项

| 项 | 状态 | 证据 |
|---|---|---|
| S1 Genome | PASS | src/causalevo/evolution/genome.py（serialize/mutate/crossover/distance/表型映射） |
| S2 Population | PASS | population.py（规则种子 + 随机组合、generation/individual_id/parent_ids 谱系） |
| S3 多目标 fitness | PASS | fitness.py：success_gain / neg_cost / neg_steps / robustness 全部来自重放测量；FitnessCache 确定性 |
| S4 NSGA-III | PASS | nsga3.py 纯 numpy：非支配排序、Das-Dennis 参考方向、归一化、niching；无外部优化库 |
| S5 进化算子 | PASS | 逐基因变异 + 均匀交叉（测试锁定范围/确定性/父母基因来源） |
| S6 基线 | PASS | B0 随机搜索 / B1 规则库 / B2 CEA-v0 / B3 NSGA-III 同预算对比 |
| S7 评估协议 | PASS | docs/PHASE3_EVOLUTION_EVAL.md（含固定超体积参考点） |
| S8 消融 | PASS | A1 无变异（best gain 0.0，证明变异必要）/ A2 单目标 vs 多目标 / A3 普通 vs A4 因果奖励 |
| S9 结果产物 | PASS | results/phase3/evolution/ 七件（含谱系、前沿、缓存） |
| 测试 | PASS | **377 passed / 0 failed / 0 skipped**（336 回归 + 41 新增） |
| 文档 | PASS | docs/PHASE3_CEA_V1_DESIGN.md、PHASE3_CEA_V1_RESULTS.md |

## 结果摘要（模拟重放，非真实模型证据）

- Pareto 前沿 6 成员，呈现轻量(0.5 gain/便宜) vs 重量(1.0 gain/更贵) 权衡；B3 的独特价值是前沿而非单点。
- 各臂在小空间均能到 1.0（如实记录）；held-out 案例上 verification 基因组泛化成功、轻量基因组失败。

## 事故与修复

- normalize() 初版返回元组错误、超体积初版实现错误 → 以已知答案的解析用例钉死（0.75 L 形等）。
- Windows 路径冒号/超长再次 → slug 消毒。
- population.py 漏 import GENES → 修复。

## 停止

停在 Phase 3.2。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。未宣称真实自进化。
