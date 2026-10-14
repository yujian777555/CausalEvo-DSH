# Phase 1.5 — 统计分析计划（G4：Live Readiness Gate 统计闸门）

冻结日期：2026-10-13（frozen 2026-10-13）。关联文档：`docs/PHASE1_R2_PILOT_DESIGN.md`（本文件是其统计部分的正式化与扩展，不重复其预算与可行性内容）、`docs/PHASE1_EXPERIMENT_PROTOCOL.md`（实验协议，本计划的冻结条款与之互锁）、`src/causalevo/eval/policy.py`（B0/B1 定义与预算对等门）。

**范围声明：本文件为统计计划文本，未发送任何真实模型请求（live API 预算 ¥0），未修改任何 src/、benchmarks/、results/ 内容。计划中所有检验规则、seed 清单、停止规则在任何 live 运行之前冻结。**

## 1. 实验设计

### 1.1 配对结构

- **同一任务双臂配对**：每个任务（26 个 microtasks，以及后续经授权的 SWE-bench pilot 实例）在 B0 与 B1 两个 arm 下各运行一次，构成一个配对观测。配对单位是 (task, seed)，不是任务池均值。
- **预算对等**：B0/B1 共享完全相同的 `Budget(max_provider_calls=2, max_total_output_tokens=2048, max_tool_calls=20, wall_time_s=300)`（`src/causalevo/eval/policy.py`），B1 的 reflection/reattempt 从同一额度扣除；对等性由 `check_budget_parity()` 强制，统计计划不接受任何绕过该门的运行数据。

### 1.2 固定 seed 清单（pre-hoc 记录）

master seed 取 **S0 = 20261010**（Phase 1 基准决策日，见 `docs/PHASE1_BENCHMARK_DECISION.md`）。派生规则与全部 seed 值在本节冻结，不得事后增删：

| 用途 | seed 值 | 说明 |
|---|---|---|
| 采样 seed 1 | 20261010 | S0 本身 |
| 采样 seed 2 | 20261011 | S0 + 1 |
| 采样 seed 3 | 20261012 | S0 + 2 |
| 执行顺序打乱 seed | 20261013 | S_ord，仅用一次，打乱后顺序写入 manifest 即锁定 |

- 主分析默认使用全部 3 个采样 seed；单 seed 敏感性子分析只允许"取 seed 1"这一种预声明子集。
- seed 只控制我方可控的采样参数与顺序打乱；provider 端不可控因素见 §5。

### 1.3 执行顺序

- (task, policy, seed) 三元组的完整执行列表在运行前以 `split_seed = S_ord = 20261013` 用确定性洗牌**只打乱一次**，打乱结果连同算法（Python `random.Random(20261013).shuffle`）写入 run manifest 的 provenance 字段，之后不再变动。
- 目的：使缓存预热、provider 负载时段、磁盘状态等顺序混杂对 B0/B1 两臂对称，而非系统地偏向某一臂。
- 中断恢复时按 manifest 中已锁定的顺序续跑，禁止重新打乱。

## 2. 主要终点（primary endpoint）

- **task_success**：单 run 的二值判定 = `visible_tests_passed AND sealed_tests_passed`（对应 `src/causalevo/eval/metrics.py` 的 `visible_tests_passed`、`sealed_tests_passed` 与 `task_succeeded` 口径；判定来自独立 Judge/DockerExecutor 的确定性 pass/fail）。
- 以 `budget_stop` / `timeout` / `invalid` 结束的 run 记为 **失败**（success=0），不得剔除；其分布作为单独的描述性指标报告。
- 次要/探索性指标（均不作显著性推断）：visible-only 通过率、provider 调用次数、输入/输出 token、成本（peak/off-peak 双口径）、wall_time、finish_reason 分布、invalid/timeout 率。

## 3. 统计分析

### 3.1 主分析：McNemar 精确检验（配对）

对每个 (task, seed) 配对，统计不一致对：

- b = B0 成功且 B1 失败 的对数
- c = B1 成功且 B0 失败 的对数

- **检验**：McNemar 精确双侧检验（以 b+c 次伯努利试验中成功 c 次的精确二项检验，H0: p = 0.5）。
- **效应区间**：不一致比例 p̂ = c/(b+c) 的 **Clopper-Pearson 精确 95% CI**，再按配对二值数据的标准变换映射回成功率差值区间。**当 b+c < 25 时必须使用精确法**（本 pilot 预计始终如此），禁止渐近卡方。
- **描述性区间**：各 arm 的边际成功率报告 **Wilson 95% CI**，仅作描述，不与对臂的区间做非配对显著性比较（那将违背配对设计）。
- **分层敏感性**：按 seed 分层重做主分析；任何"剔除某个预声明 seed 后效应方向翻转"的情况必须如实写入结果文档。

### 3.2 成本与 token 差值：配对 bootstrap

- 对每配对的成本差（B1 − B0，peak 与 off-peak 双口径分别计算）、输入 token 差、输出 token 差、provider 调用次数差，做 **配对 bootstrap**：以任务（配对单位）为重采样单位，**10,000 次重采样**，报告差值中位数及 2.5%/97.5% 百分位区间。
- 该分析为描述性（成本对等性核查），不设显著性阈值；若成本差区间不含 0，仅触发预算包络复核，不触发任何模型层面结论。

### 3.3 数据质量门槛（先于任何检验）

汇总表（`summarize_traces` 口径）中若任一 arm 出现：requested ≠ executed、invalid 率 > 10%、或 timeout 率 > 30%，则判定为**管线无效运行**，该批次全部结果只用于工程排障，不进入 §3.1/§3.2 分析。此门槛与 `docs/PHASE1_R2_PILOT_DESIGN.md` §5 的 floor effect 防护并列执行。

## 4. 多重比较规则

- **唯一主比较**：B0 vs B1（后续扩展时：各基线 vs CausalEvo），且**仅限 task_success 终点**。主比较在每个实验批次内只有一个，不做多重性校正之外的任何"挑显著"空间。
- §2 列出的全部次要指标、所有分层/子集分析、所有成本/token 分析一律标注为 **exploratory**，其结果不得用于支持任何确认性结论。
- 若未来同一批数据上出现多个主比较（如 B0 vs CausalEvo、B1 vs CausalEvo 并行），采用 Bonferroni 校正并在结果文档中声明校正前后两套 p 值；本条在本 pilot（单一主比较 B0 vs B1）下不激活，仅预声明。

## 5. Provider 随机性声明

- **模型固定**：所有 live 运行固定同一 model id（当前为 deepseek-flash = DeepSeek-V4.1-Flash，价格快照见 `src/causalevo/pricing.py`），model id 与 `ProviderEndpoint` 配置写入每次运行的 manifest。
- **时间戳记录**：每次 provider 调用的请求/响应时间戳逐条记录，用于事后检查服务端负载时段的混杂。
- **不可控漂移**：provider 未承诺按 seed 可复现的采样（NOT_VERIFIED）；模型版本更新、服务端解码栈变更、负载相关非确定性均不受我方控制。配对 seed 只能对齐我方输入，**不能**消除服务端漂移。因此全部结论以"工程证据 + 区间估计"口径表述，不作确定性因果断言；观测到的效应若在逐日分层下方向不一致，必须如实报告。

## 6. 停止规则

- **禁止窥视式提前停止**：不得在观察到"已显著"或"已无希望"后提前终止或追加样本。样本量（26 microtasks × 2 arms × 3 seeds）在运行前冻结，运行到完成或触发的只有下列工程性中止。
- **预算耗尽中止**：累计计费达到该批次预先记录的授权额度（价格口径见 `docs/PHASE1_R2_PILOT_DESIGN.md` §4）时，立即停止派发新 run；已完成的配对进入分析，未配对的单边 run 标记为不完整配对并剔除出主分析（仅作描述）。
- **floor effect / 管线中止**：触发 §3.3 数据质量门槛或 `docs/PHASE1_R2_PILOT_DESIGN.md` §5 的 floor effect 条件时中止并上报 Planner；中止前的数据不用于任何确认性推断。
- 任何中止事件连同触发条件、已完成 run 清单写入结果文档。

## 7. 反钓鱼条款（anti-fishing）

- 本计划与 `docs/PHASE1_EXPERIMENT_PROTOCOL.md` 互锁：**终点定义、主比较、检验方法、seed 清单、样本量、数据质量门槛、预算包络在任何 live 运行之前冻结**（本文件标注 frozen 2026-10-13）。
- 冻结后对上述任一项的修改，必须：(a) 以新文档或修订版本显式标注修改日期与原因；(b) 将受影响分析整体标注为 **exploratory**，不得再以 confirmatory 口径呈现；(c) 保留冻结版原文可查（git 历史 + 结果文档引用具体 SHA）。
- 事后构造的终点、事后选择的子集、事后调整的阈值，一律 exploratory。结果文档的确认性结论只允许引用本计划预声明的分析。

## 8. 检验效能说明（power note）

- 26 个 microtasks 下，McNemar 检验的有效信息量来自不一致对数 b+c；即使不一致对占一半（13 对），精确检验也只能检测到非常大的效应（粗略地，|成功率差| 需达到约 0.3–0.4 量级才可能在 α=0.05 双侧达到可接受的检验效能）。本 pilot 的可检测效应是**粗糙的**。
- 因此本 pilot 的定位是**管线有效性验证**（配对执行、预算对等、judge 一致性、manifest 完整性、成本包络实测），而非统计显著性产出。p 值与区间照常报告，但"p 不显著"不得解读为"两臂无差异"，"p 显著"也需结合 §5 的不可控漂移声明谨慎表述。
- 若未来需要确认性结论，须先基于本 pilot 的不一致对比例做正式样本量估算，并另行冻结新的统计计划。

## 9. 边界声明

本文件仅为统计计划：撰写与冻结过程中未发送任何真实模型请求，未运行任何 live 评测，无任何成功率数字。任何 live 执行仍需 `require_live_authorization()` 授权（`DEEPSEEK_API_KEY` + `CE_DSH_LIVE_AUTH=phase1-pilot`），并受 `docs/PHASE1_EXPERIMENT_PROTOCOL.md` 与本计划的双重冻结约束。
