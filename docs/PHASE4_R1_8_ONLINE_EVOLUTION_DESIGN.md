# CE-DSH-P4-R1.8/R1.9 — Online Evolution Controller 设计（实现前冻结）

日期：2026-10-21。状态：设计冻结（R1.8 Task B3 要求：实现前先写设计）。本控制器是 **L2/L3 运行时在线演化**；**不是 L4 递归自我改进**（演化算子与评价器在本设计中恒定）。

## 1. 目标与边界

在真实 Agent 任务序列上，把"已结算 episode 结果"转化为"后续策略选择的变化"：

```
任务执行 → 独立 Judge 评价 → 费用/调用结算 → observe() 更新 → 后续 select() 发生变化 → （周期）演化步骤产生新候选
```

明确不做：L4（算子/评价器自我修改）、LLM 自评分、CoT/密封测试内容输入。

## 2. 状态（State / Context）

仅使用干预前可观察特征：

```
context = {
  "failure_type":  ∈ {tool, verification, planning, knowledge, infra, none}   # 由 outcome1.failure_kind + invalid_reason + edited 派生（规则冻结，见 §7）
  "edited":        bool,   # workspace digest 变化
  "invalid":       bool,   # judge invalid_reason
  "failure_kind":  str,    # none|provider_error|timeout|budget_stop|transport|protocol|invalid|unknown_cost
}
```

无 CoT、无 sealed 测试内容、无未来 episode。

## 3. 候选与有效表型

- 初始化：manifest 校验通过的冻结 Pareto 前沿（`configs/phase3_artifact_manifest.json`；校验失败即 fail-closed 拒绝启动）。
- **有效表型** = `genome.phenotype_transforms()` 的元组（`genome.py:81-92`）；reserved 基因（`reflection_step`、`retry_strategy`）不产生表型，**不计入**表型身份（如实披露，不冒充多样性）。
- 种群 = 按有效表型去重的候选档案，有界（默认 ≤16）。

## 4. 选择（select）

每个候选 c 维护按 context.failure_type 分桶与全局的测量统计：n、successes、costs、calls。

分数（确定性的乐观选择）：

```
score(c, ctx) = rate(c, ctx) − λ_cost·mean_cost(c) − λ_calls·mean_calls(c) + β·unmeasured(c)
rate(c, ctx)  = ctx 桶有样本时：bucket 成功率（Laplace 平滑 (s+1)/(n+2)）
                无样本时：全局成功率（无则视为未测）
unmeasured(c) = 1 if c 从未被观察 else 0
```

- β（探索奖励）= 0.05；λ_cost = 50（每 CNY），λ_calls = 0.02。
- 并列时按 genome_id 字典序（确定性）。
- select 返回 `{genome, genome_id, phenotype, reason, policy_version, population_version}`；每次 observe/evolve 使 population_version 单调 +1。

## 5. 观察（observe）

```
observe(episode_id, context, genome_id, outcome)   # outcome = {success, cost_cny, calls, failure_kind}
```

- 恰好一次：重复 episode_id → fail-closed（拒收并标记）；乱序反馈允许（episode 顺序以事件日志为准回放）。
- `failure_kind ∈ {unknown_cost, budget_stop, transport, protocol}` → **基础设施结局**：不产生行为奖励更新、不重试，仅记录。
- cost_cny 未知（None）→ 进入非学习停止状态（fail-closed）。
- 每条观察追加到事件日志（JSONL，可序列化、可重放）。

## 6. 演化步骤（evolve）

每积累 `update_every`（默认 4）条新的行为观察后执行一次：

1. 对**已测量**候选构造多目标适应度向量：`[success_rate, −mean_cost, −mean_calls]`。
2. `nsga3_select`（复用冻结 `nsga3.py`）选父母。
3. 交叉 + 变异（`genome.mutate(p=mutation_p=0.25)`）产生 `n_offspring=4` 个后代。
4. 按有效表型去重；档案超过 16 时，`nsga3_select` 选幸存者（未测量后代受保护一期：不参与淘汰直至被测量一次）。
5. 后代带 parent_ids 与 generation；population_version +1。

未测量候选不得被视为已证实最优（其统计未更新，仅靠探索项获得试用）。

## 7. context 派生规则（冻结）

```
failure_kind ∈ {unknown_cost,budget_stop,transport,protocol} → infra
invalid_reason 非空                                          → verification
未编辑（edited=False）                                       → planning
failure_kind == provider_error                               → tool
其余                                                          → knowledge
```

## 8. 序列化与确定性

- `state_dict()`：候选档案（genome、谱系、统计、表型键）、事件日志位置、policy/population 版本、RNG 种子、配置哈希。
- 配置（max_population、update_every、mutation_p、β、λ_cost、λ_calls、seed、manifest 哈希）冻结于运行 manifest 的 `controller_config`，SHA-256 记录。
- `replay(events)`：从初始状态按事件日志重放 → 状态逐字节一致（测试证明）。
- `history_up_to(t)`：只含 t 之前事件的选择视图（无未来泄漏）。

## 9. 超参数冻结

| 参数 | 值 |
|---|---|
| max_population | 16 |
| update_every | 4 |
| mutation_p | 0.25 |
| n_offspring | 4 |
| exploration β | 0.05 |
| λ_cost | 50.0 |
| λ_calls | 0.02 |
| seed | 20261021 |

不在验证/测试结果上调参。

## 10. 与历史臂的区分

- B5-v1（本 pilot）：冻结 Pareto 静态选择（`CausalPolicyAdapter.cea_v1_from_manifest` + `select_genome`），全程零更新。
- CEA-v2：本控制器（在线更新 + 周期演化）。
- 二者不同名、不同代码路径、不同 policy_version 记录，互不混淆；历史 B4/B5 行不改名不回填。
