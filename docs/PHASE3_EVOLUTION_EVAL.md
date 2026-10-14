# Phase 3.2 评估协议（docs/PHASE3_EVOLUTION_EVAL.md，冻结）

日期：2026-10-14。实现：scripts/run_evolution.py。

## 1. 指标（冻结）

### Optimization Quality
- best Pareto success gain：前沿上 success_gain 最大值。
- hypervolume：最终前沿对固定参考点 (-0.5, -0.01, -6.0, -0.1) 的超体积（参考点记录于 manifest/本文，变更即新版本）。
- Pareto front size。

### Efficiency
- evaluations：评估的基因组数（fitness_cache 行数）。
- generations、wall cost（容器运行时长由运行日志记录）。

### Generalization（时间/案例切分）
- 训练：bad_tool_blocks_write + broken_write；测试：held-out wrong_fix。
- 报告前沿成员在 held-out 案例上的 test_fitness。

## 2. 基线（冻结）

B0 随机搜索（同预算）、B1 规则库种子基因组、B2 CEA-v0（LinUCB 策略映射回基因组，同训练态测量）、B3 NSGA-III。

## 3. 消融（冻结）

A1 无变异（p=0）；A2 单目标（只 success gain）vs 多目标；A3 普通 outcome（cf_success）vs A4 因果差值（success_delta）。

## 4. 纪律

- 指标、参考点、案例切分在见结果前冻结；事后改动标 exploratory。
- 所有适应度来自重放测量；不声称真实模型改善。
