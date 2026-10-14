# Phase 3.2 CEA-v1 结果（离线，零费用）

日期：2026-10-14。适应度全部来自容器重放测量；**模拟干预机制，非真实模型改善证据**。

## 1. Pareto 前沿（train：bad_tool_blocks_write + broken_write）

最终前沿 6 个成员，两个不同适应度点（其余为重复表型）：

| 适应度点 | success_gain | cost | steps | robustness | 代表基因组 |
|---|---|---|---|---|---|
| 轻量 | 0.5 | -0.00024 | -1.0 | 0.5 | read_before_write=1 |
| 重量 | 1.0 | -0.00054 | -2.0 | 1.0 | tool_validation+verification_level=2 等组合 |

前沿明确呈现"轻量便宜修一半 vs 重量全修更贵"的权衡——这正是多目标的存在意义。

## 2. Baseline 对比（baseline_comparison.json）

| 臂 | best train fitness | held-out test fitness（wrong_fix） |
|---|---|---|
| B0 随机搜索 | [1.0, -0.00054, -2.0, 1.0] | [1.0, …, 1.0]（碰巧选中有效组合） |
| B1 规则库 | [1.0, -0.00054, -2.0, 1.0] | [1.0, …, 1.0] |
| B2 CEA-v0 | [1.0, -0.00054, -2.0, 1.0] | 状态条件策略（见注） |
| B3 NSGA-III | 前沿 6 成员，含 [1.0, …, 1.0] | 轻量成员 0.0 / 重量成员 1.0 |

如实说明：搜索空间小（表型仅约十余种），各臂都能找到最优点；B3 的独特产出是**显式 Pareto 前沿**（替代方案及权衡），不是更高的单点。B3 hypervolume(train)=0.0690（参考点 (-0.5,-0.01,-6.0,-0.1)，见 PHASE3_EVOLUTION_EVAL.md）。

## 3. 消融（ablation_results.json）

- A1 无变异：best success_gain = 0.0 —— 无变异时交叉无法跳出种子区，变异是必要的。
- A2 单目标 vs 多目标：单目标 best gain 同为 1.0，但不产出前沿（权衡消失）。
- A3 普通 outcome 奖励：robustness=1.0（虚高，口径问题同 P3.1）；A4 因果差值正常。

## 4. 泛化

held-out wrong_fix 案例上：含 verification 基因的重量基因组成功（test fitness [1.0,…]），仅 read_before_write 的轻量基因组失败（0.0）—— 符合机制直觉，样本极小，仅描述性。

## 5. 产物

results/phase3/evolution/{evolution_manifest, population_history, pareto_front, fitness_history, baseline_comparison, ablation_results, fitness_cache}。

## 6. 限制

1. 表型空间小且离散；前沿的"发现"实为机制覆盖。
2. 适应度来自模拟重放。
3. 无 live 数据；无 holdout；无 CoT。
