# Phase 3.1 CEA 设计（Contextual Bandit 因果干预选择）

日期：2026-10-14。范围：CEA-v0 工程与离线仿真。**不实现** PPO/RLHF/Prompt 进化/微调/自动改模型参数；不宣称 Agent 已自进化成功。

## 1. 定位

论文主线首次闭环：Failure → Intervention 候选群 → 因果奖励 → 策略更新 → 未来选择改善。本阶段交付算法定义、控制器、离线仿真与对照；真实任务上的有效性依赖后续已授权的 live pilot。

## 2. 组件（src/causalevo/evolution/）

- `bandit.py`：disjoint LinUCB（纯 numpy，确定性，可序列化）。
- `policy.py`：B0 RandomPolicy / B1 RulePolicy（taxonomy 映射）/ B2 LinUCBPolicy；固定状态向量布局（one-hot failure_type + 归一化任务特征 + 可选历史块）。
- `reward.py`：`reward = success_delta − λ·max(0, cost_delta_cny)`（λ=100；奖励来自反事实测量差，不是模型输出）。
- `memory.py`：EpisodeMemory（严格递增 episode_id；history_up_to 结构性排除未来）。
- `controller.py`：CausalEvolutionController.select_intervention / record_and_update（先记 episode 再更新；置信度 = top-2 分数 margin 分档；policy_version = 状态哈希）。

## 3. 离线仿真（scripts/run_cea_simulation.py）

- 奖励矩阵：`results/phase3/replay_sweep/sweep_results.jsonl`（3 场景 × 2 任务 × 7 干预 = 42 行完整配对测量，容器真实重跑）。
- episodes：6 个失败态 × 10 轮 = 60，严格时间序；rounds 0–6 训练、7–9 只评估不更新（时间切分泛化）。
- 臂：B0 random / B1 rule / B2 LinUCB；消融：A1 无历史 vs A2 有历史；A3 普通 outcome 奖励 vs A4 因果差值奖励。

## 4. 假设

1. 状态空间小且平稳（6 态）——仿真只验证管线与学习机制，不产生统计功效。
2. 重放矩阵的奖励是模拟机制的结果；真实分布待 live pilot。
3. λ=100 是口径选择，记录在 algorithm_config.json，可复现。

## 5. 限制

- 不建模跨任务迁移；failure_type 外的状态特征较粗。
- LinUCB 线性假设 vs 真实奖励结构的差距未知。
- 无 live 数据；无 holdout 使用；无 CoT 输入。
