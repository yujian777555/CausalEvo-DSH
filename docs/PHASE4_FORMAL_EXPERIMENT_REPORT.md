# Phase 4 正式实验报告 — CE-DSH-P4-R1.9 真实 DeepSeek 四臂在线演化 pilot

日期：2026-10-25。Executor：Kimi。授权：用户显式批准真实 API 调用，**硬上限 ¥2.00**。证据等级：**探索性 pilot**（26 任务簇 / 52 任务-种子对；microtasks 为工程任务，非论文 unseen test）。

协议：`docs/PHASE4_R1_9_EXPERIMENT_PROTOCOL.md`（执行前冻结；final_success 主终点、配对 McNemar + 任务簇 bootstrap、per-scope cap=8、全局 ¥2.00）。实现提交：`45c51eb66c2c30ef34693278f15cf415193c3424`。

## 1. 真实 API 调用与费用

| 项 | 值 |
|---|---|
| 本轮真实 DeepSeek 模型调用（完成+可计量请求） | **912 次**（24 canary + 2 早期 canary 异常 + 13 中断 run1 + 180 中断 run2 + 693 正式 pilot 及续跑，SETTLED 计） |
| 本轮总费用（peak 口径，proxy 结算） | **¥1.306339** |
| 未知费用请求 | 1 次（`fe088dd586454e9296aef973143a258a`，SSE IncompleteRead），按 worst-case 预留上界 **¥0.157041** 计入 |
| **合计（含未知上界）** | **¥1.463380（< ¥2.00 硬上限）** |
| 账本 | 每次 run 的 `proxy-ledger/ledger.jsonl` 完整（RESERVED→SENT→SETTLED/UNKNOWN/REJECTED），费用独立按 run 记录，未重置 |

说明：peak 为保守上界；行级 off-peak 报告见 analysis.json。中断/失败 run 的费用全部计入（无账本重置）。

## 2. 四臂是否真实执行？——是

| 臂 | 代码路径 | 行数 | 说明 |
|---|---|---|---|
| B0-original | run_row 单次尝试 | 52 | 无重试 |
| B1-random | `rng.choice(sorted(INTERVENTION_TEXT))` | 52 | 冻结随机源 |
| B5-v1-frozen-pareto | `CausalPolicyAdapter.cea_v1_from_manifest` + `select_genome` | 52 | 全程零更新 |
| CEA-v2-online | `OnlineEvolutionController`（select→observe→evolve） | 52 | 在线更新 |

每行含 `policy_version`、`selected_genome_id`、`selection_reason`、`intervention_text`。非历史 B4/B5 代理/bundle。

## 3. CEA-v2 是否实际在线更新？——是

- `observed_rows`（行为观察）= 4（CEA-v2 仅 4 行 attempt-1 失败且重试），`evolve_events` = 1（第 4 条观察后 NSGA-III 演化步骤）。
- `distinct_selected_genomes` = 5，`distinct_population_versions` = {0, 1}（版本随演化前进）。
- `events.jsonl` 含 evolve 事件与 parent/offspring 谱系；`controller_state.json` 含候选统计。在线更新链条：`任务→Judge→账本结算→observe→evolve→后续选择变化`。
- 注意：CEA-v2 的 attempt-1 成功率 0.846（44/52），仅 8 行失败、其中 4 行重试产生行为观察，学习信号有限（如实披露）。

## 4. 在线更新是否影响后续策略选择？——是

- 选中基因组从初始探索（unmeasured）转为按已测量统计选择，并产生新子代（born_generation=1, parent_ids 记录）。事件与行记录可复核。

## 5. 相对随机/静态策略是否有提升？——**没有证据（负面结果）**

| 比较 | 配对差 | 不一致对 (+/−) | McNemar p | Holm p | 95% CI（任务簇 bootstrap） | 提升证据 |
|---|---|---|---|---|---|---|
| CEA-v2 vs B1-random | −0.038 | 2/4 | 0.6875 | 1.0 | [−0.154, 0.058] | **无** |
| CEA-v2 vs B5-v1 | −0.038 | 2/4 | 0.6875 | 1.0 | [−0.115, 0.038] | **无** |
| CEA-v2 vs B0-original | +0.038 | 5/3 | 0.7266 | 1.0 | [−0.058, 0.135] | **无** |
| B5-v1 vs B1-random | 0.000 | 3/3 | 1.0 | 1.0 | [−0.096, 0.096] | **无** |

各臂最终成功率：B0 0.8269 / B1-random 0.9038 / B5-v1 0.9038 / CEA-v2 0.8654。首轮成功率：B0 0.8269 / B1 0.8654 / B5-v1 0.8269 / CEA-v2 0.8462。恢复率（分母为重试行）：B1 2/6、B5-v1 4/9、CEA-v2 1/4。

## 6. 提升是否有统计支持？——**否**

主比较不一致对很少（2/4），功效有限，故标注探索性 pilot。所有比较 CI 跨 0、p>0.05（Holm）。**不得宣称 CEA-v2 优于随机或静态策略**；与历史 Phase 4 的负面结论一致。

## 7. 每单位费用效果

| 臂 | 最终成功率 | off-peak 费用 | provider 请求 | 成功率/¥ |
|---|---|---|---|---|
| B0-original | 0.8269 | ¥0.119527 | 163 | 6.92 |
| B1-random | 0.9038 | ¥0.122124 | 180 | 7.40 |
| B5-v1-frozen-pareto | 0.9038 | ¥0.133524 | 185 | 6.77 |
| CEA-v2-online | 0.8654 | ¥0.122265 | 171 | 7.08 |

B1-random 的单位费用成功率最高；CEA-v2 不优于它。

## 8. 在线更新前后行为变化与消融

- 在线更新使选中基因组集合从初始冻结前沿扩展为含子代的集合（distinct_selected_genomes=5，含 born_generation=1 个体）。
- 消融（离线，不花真实预算）：`results/phase4/cea_v2_offline/run-20261024T151552Z`（合成机制验证，4500 episodes）包含 no_update / no_variation / no_context / single_objective；`iid_noise` 负对照各臂 regret 均为 0；全周期无 livelock 截断。合成结果为机制证据，**不是**真实模型性能证据。

## 9. 哪些结论仍不能证明

- 不能证明 CEA-v2 在真实模型上优于随机干预或静态 Pareto 策略。
- 不能证明递归自我改进（L4 未实现；本 pilot 仅 L2/L3 在线更新）。
- 不能作论文级确认性评估（小样本、工程任务、探索性 pilot）。
- 不能宣称 NSGA-III 本身带来收益（本 pilot 只有 1 次演化步骤，信号有限）。

## 10. 执行链与 fail-closed 记录（诚实披露）

- canary 通过（8 行）→ 完整 pilot 经历多次中断：**Windows 文件锁竞态**（publish/ack 两侧已加固并重试）、**SSE IncompleteRead → unknown_cost 全局停止**、**控制器 livelock（合成验证发现）→ 修复后重启**、**陈旧 control.json 高 generation 导致 ACK 超时 → 启动清理**。
- 续跑机制：`--resume`（账本重放恢复已结算费用与 scope 计数、控制器事件重放恢复学习状态、按 scope 人工对账并记录原因、扣除未知费用上界的剩余 cap）。**未知费用未清零、历史行未合并重复**。
- 最终 208 行完整，aborted=None；所有失败样本保留。

## 附：数据与可复现性

- 正式数据：`results/phase4/live2/phase4-r19-pilot-20261024T151323Z/`（tasks.jsonl 208 行、events.jsonl、controller_state.json、manifest.json、proxy-ledger/ledger.jsonl、analysis.json）。
- 离线验证：控制器 16 tests、agent smoke 6 tests、合成驱动 14 tests、分析 4 tests；全量 pytest 见 executor_report。
- 历史 312 行与 Phase 0–3 冻结工件未修改；本轮行与历史行不合并。
