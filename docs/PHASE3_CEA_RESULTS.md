# Phase 3.1 CEA 结果（离线仿真，零费用）

日期：2026-10-14。数据：results/phase3/replay_sweep（42 行配对测量）驱动的离线 episodes（60 = 6 态 × 10 轮；评估窗 rounds 7–9 不更新）。**所有数字是重放矩阵上的策略学习证据，不是真实模型改善证据。**

## 1. Baseline 对比（评估窗，n=18）

| 臂 | top-1 选择准确率 | 成功干预率 | 平均奖励 | 平均 regret |
|---|---|---|---|---|
| B0 random | 0.056 | 0.389 | 0.370 | 0.594 |
| B1 rule | 0.667 | 1.000 | 0.964 | 0.000 |
| B2 CEA-v0 (LinUCB) | 1.000 | 1.000 | 0.964 | 0.000 |

- B2 在评估窗收敛到 oracle 动作（top-1 = 1.0，regret=0）；B1 的 top-1 低是因为它不看成本差（规则命中类别但不挑同类最优）。
- 学习曲线见 results/phase3/cea/learning_curve.json（B2 累计 regret 在训练轮内趋平）。

## 2. 消融

| 消融 | top-1 | 平均奖励 |
|---|---|---|
| A1 无历史 | 1.000 | 0.964 |
| A2 有历史 | 0.722 | 0.949 |
| A3 普通 outcome 奖励 | 1.000 | 1.000 |
| A4 因果差值奖励 | 1.000 | 0.964 |

- A2（历史）略差于 A1：平稳小状态空间下历史特征只加噪声——如实记录：经验记忆在此环境无价值。
- A3 的 1.0 是假象：普通 outcome 忽略原始臂本就失败的事实（本案例原始臂恒失败），说明普通奖励高估有效性；因果差值奖励（A4）扣除了成本/基线。该对比仅为口径演示。

## 3. 产物

results/phase3/cea/{algorithm_config, episode_history, baseline_results, learning_curve, ablation_results}（.json/.jsonl）；results/phase3/replay_sweep/{sweep_results.jsonl, manifest.json}。

## 4. 限制（如实）

1. 6 个失败态、每态一轮即收敛——学习难度平凡；仅证明管线与时间纪律正确。
2. 奖励来自磁带变换模拟的干预机制。
3. 无 live 数据、无 holdout、无 CoT。
