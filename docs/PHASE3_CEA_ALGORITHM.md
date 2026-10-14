# Phase 3.1 — CEA-v0 算法定义（冻结）

日期：2026-10-14。实现：`src/causalevo/evolution/`。**禁止** PPO/RLHF/Prompt 进化/微调/自动改模型参数。

## 1. 问题形式化

研究问题：Agent 能否利用失败的因果反馈，学习选择更有效的干预策略？

## 2. State（失败上下文）

`failure_state = {failure_type（7 类 one-hot）, prompt_chars/2000, n_visible_checks/10}`；消融 A2 追加每动作历史奖励率。状态只含可观测轨迹/任务字段，无 CoT。

## 3. Action

干预库中的 `intervention_id`（7 个，见 src/causalevo/intervention/generator.py 的 INTERVENTION_LIBRARY；含 no-op）。每 episode 的候选集固定为该库。

## 4. Reward（因果奖励）

`reward = success_delta − λ · max(0, cost_delta_cny)`，λ=100（写入 algorithm_config.json）。
- success_delta 与 cost_delta 来自 Phase 2.3 式配对反事实重放测量（本阶段为 results/phase3/replay_sweep 的完整矩阵）。
- **reward 不是模型输出**；它是干预前后受控结果差。
- λ 的选取是口径假设（记录并可复现），成本为磁带世界合成计量。

## 5. Update（Contextual Bandit）

B2 实现 disjoint LinUCB（每动作独立 ridge + UCB 奖励，α=0.5）：
- 选择：argmax_a (θ_a·x + α√(xᵀA_a⁻¹x))；
- 更新：A_a += xxᵀ，b_a += r·x（仅在被选动作上）。
- 纯 numpy、确定性、可序列化（to_dict/from_dict）。

## 6. 时间纪律

- episode_id 严格递增；`EpisodeMemory.history_up_to(t)` 结构性排除未来。
- 评估窗口（rounds ≥ 7）只记录不更新（eval-no-update）。
- 泄漏由 tests/test_evolution_controller.py::test_no_future_leakage_in_history_rates 等锁定。

## 7. 停止与边界

- 不实现种群进化/多目标搜索（属 Phase 3.2 候选）。
- 本阶段结论仅覆盖"离线回放矩阵上的策略学习管线"。
