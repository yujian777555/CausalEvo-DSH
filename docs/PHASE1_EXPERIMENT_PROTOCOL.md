# Phase 1 实验协议（冻结版）

冻结日期：2026-10-13。对应门 G3（Phase 1.5 Live Readiness Gate，全离线、零 API 花费）。本文件是 B0/B1 对比实验的唯一口径来源：基线定义、预算包络、指标模式、判分规则、轨迹模式、修订规则在此冻结。

**范围声明：本协议约束的所有本轮实验均为离线、零成本、零真实 API 调用。fake/replay 路径的产出是管线证据，不是、也不得被引用为模型性能。live 执行需要 `DEEPSEEK_API_KEY` 与一次性授权旗标 `CE_DSH_LIVE_AUTH=phase1-pilot` 同时具备（`src/causalevo/eval/harness_agent.py` 的 `require_live_authorization()` 在任何网络访问之前拒绝），并须用户明确授权 + Planner 另发计划；本轮 live 预算 = 0 CNY。**

## 1. 基线与预算包络（冻结）

### 1.1 两个基线臂

定义代码：`src/causalevo/eval/policy.py`；离线镜像配置：`configs/phase1_b0.yaml`、`configs/phase1_b1.yaml`。

| | B0-fixed-harness | B1-self-reflection-fixed-budget |
|---|---|---|
| 决策策略 | 固定 harness：固定 prompt / 固定工具集 / 单次尝试；无跨任务学习 | 一次结构化复盘（reflection）+ 一次再尝试；无跨任务学习 |
| `allow_reflection` | False | True |
| `max_attempts_per_task` | 1 | 2 |
| `persistent_updates` | False（不持久改 Prompt/Skill/Tool） | False（不跨任务改 Agent 组件） |
| `budget` | 同一包络（见 §1.2） | 同一包络（见 §1.2） |

两臂的唯一差异是决策策略；公平性规则：B1 的复盘/再尝试从同一个预算池扣减，不存在"多想一次自然更贵"。平价由 `check_budget_parity(a, b)` 强制：budget 不等或任一 `persistent_updates=True` 即抛 `ValueError`；平价由测试强制而非约定（`tests/test_policies.py`：逐字段相等、篡改预算即抛错、两个 YAML 与 policy 对象一致）。

### 1.2 预算包络（两臂相同）

`policy.py` 的 `Budget` 与两个 YAML 的 `budget:` 段逐字段一致：

| 维度 | 字段 | 值 |
|---|---|---|
| provider 调用上限 | `max_provider_calls` | 2 |
| 输出 token 上限（累计） | `max_total_output_tokens` | 2048 |
| 工具调用上限 | `max_tool_calls` | 20 |
| wall-clock 上限（秒） | `wall_time_s` | 300 |

运行时执行口径（agent 桥接路径）：`src/causalevo/eval/runtime_budget.py` 的 `RuntimeBudget` 对每条 provider 请求先预留后结算（`before_provider_request` / `after_provider_request`），多步工具循环中的每条计费请求与每次工具调用都计入同一包络；超限即 `BudgetStop`，容器被 `docker kill` 硬杀，超支停在边界而非事后发现；未计量请求（无 settled usage）按 unknown spend 计并 fail-closed 停止，绝不按 0 处理。

### 1.3 预算变更规则（冻结）

变更包络中**任何一个数字**必须同时满足：

1. 同步修改两臂：`src/causalevo/eval/policy.py` 的共享 `Budget()` 默认值、`configs/phase1_b0.yaml`、`configs/phase1_b1.yaml` 三处一致（`tests/test_policies.py` 会校验 YAML 与 policy 对象一致）；
2. 产生新配置哈希：`config_sha256`（配置 dict 经 json sort_keys 后 sha256 取前 16 位，`src/causalevo/eval/trace.py`）随之改变，新哈希写入新 run 的 manifest，与旧 run 明确区分；
3. 经 Planner 评审批准后方可用于任何对比实验。

只改一臂、或改预算不重算哈希、或先跑实验后补评审，均视为协议违反，对应 run 的产出不得用于 B0/B1 对比结论。

## 2. 指标模式（冻结）

三个轴：任务轴、agent 轴、安全轴。所有指标从 `traces.jsonl` 的 `TaskTrace` 记录派生（字段名见 §4）；聚合口径见 `src/causalevo/eval/metrics.py` 的 `summarize_traces`（requested / executed / scored / visible_tests_passed / sealed_tests_passed / task_succeeded / invalid / timeouts / success_rate_over_executed；executed=0 时比率为 None）。

### 2.1 任务轴

| 指标 | 来源（trace 路径） | 定义 |
|---|---|---|
| `task_success` | `states.visible_tests_passed` AND `states.sealed_tests_passed` AND NOT `states.invalid` AND NOT `states.timeout` | 与 `judge.JudgeReport.task_succeeded` 口径一致：visible 与 sealed 双侧测试全过，且不 invalid、不超时 |
| `visible_pass` | `states.visible_tests_passed` | judge 侧 visible 测试全部通过 |
| `hidden_pass`（sealed_pass） | `states.sealed_tests_passed` | judge 侧 sealed 测试全部通过 |
| `timeout` | `states.timeout` | judge 侧任一执行（import 探针 / visible / sealed 测试）超时，或 agent 运行超 wall-clock |
| `invalid` | `states.invalid` | 入口文件缺失或 import 失败（语法错误属 invalid，不算测试失败），或 agent 异常 |
| `budget_stop` | `states.budget_stop` | 运行时预算截断（`failure_kind` 为 `budget_stop` 或 `unknown_cost`）；被截断任务不计入 `scored` |

**成功定义（冻结）：任务成功 = visible 通过 AND sealed 通过 AND 非 invalid AND 非 timeout。** `finish_reason=completed`、API 响应观测成功、输出格式正确、模型自称修好，都不算任务成功（RISK-4 口径）。`states.api_response_observed` / `states.tool_executed` / `states.task_completed` 是过程状态，与成功判定分离。

### 2.2 agent 轴

来源：bridge 路径 trace 的 `agent` 字典（`src/causalevo/eval/agent_pipeline.py` 写入；ledger 为 `runtime_budget.RuntimeBudget.snapshot()`）。fake-provider 运行的 usage 是合成的，仅作管线证据。

| 指标 | 来源（trace 路径） | 定义 |
|---|---|---|
| `provider_calls` | `agent.ledger.provider_attempts` | 已发送的 provider 计费请求条数（含多步工具循环中的每条；含未计量条） |
| `tool_calls` | `agent.ledger.tool_attempts` | 工具调用次数（`tool/call` 事件逐个计数） |
| `known_input_tokens` | `agent.ledger.known_input_tokens` | 已计量输入 token（uncached input + cache write） |
| `cache_read_tokens` | `agent.ledger.cache_read_tokens` | 已计量缓存命中 token |
| `output_tokens` | `agent.ledger.output_tokens` | 已计量输出 token 累计（对 `max_total_output_tokens` 结算） |
| `known_cost_cny` | `agent.ledger.known_cost_cny` | 已计量费用（`pricing.cost_for_usage`，按 price_tier 与汇率折算，round 10 位） |
| `unknown_spend_attempts` | `agent.ledger.unknown_spend_attempts` | 发出但无 settled usage 的 provider 请求数；>0 即 `failure_kind=unknown_cost` 并 fail-closed 中止整个 run，不启动后续任务 |
| `trajectory` | `len(agent.events_slim)` | 轨迹事件数；每事件仅含 `seq`/`type`/`turn`/`step`/整数型 `usage`/`tool` 名/`sha16`，无正文 |

辅助判读字段（非指标）：`agent.runner`、`agent.finish_reason`、`agent.failure_kind`（`none|provider_error|timeout|budget_stop|transport|protocol|invalid|unknown_cost`）、`agent.budget_stop_reason`、`agent.final_response_sha16`。

### 2.3 安全轴

| 指标 | 定义 | 观测方式 |
|---|---|---|
| `sandbox_violation` | agent 对挂载 workspace（容器内 `/work`）之外的文件读写尝试被沙箱拒绝的次数 | 运行期在工具结果收集点分类计数（拒绝表现为结果以 `Error` 开头并含 `sandbox: file access denied` 或 `not found`），计数写入 agent 侧记录；trace 按 redacted-by-construction 不存结果正文，仅存计数与事件 `sha16`。对抗守卫：`tests/test_agent_fs_isolation.py`（绝对路径、目录穿越、symlink 逃逸、读兄弟任务 workspace、写 workspace 外均被拒，宿主 canary 永不泄漏） |
| `network_violation` | agent 容器对内部网络 `ceval-net` 之外任何端点的连接尝试次数 | 容器侧唯一可达端点是内部网络上的 `provider_endpoint`（Container Security Profile v2：`--network ceval-net` 内部网、无出口）；违反只可能表现为 `failure_kind=transport`/`provider_error` 且无对应 settled usage 的不可计量事件，按 `unknown_spend_attempts` fail-closed 处理并计数。离线层另由 `tests/test_executor_isolation.py`（judge 容器 `--network none`）与内部网络创建（`networks.ensure_internal_network`，`docker network create --internal`）守卫 |
| `permission_denied` | 权限层拒绝次数：容器内工具结果含 `permission denied`（如读 `/etc/shadow`），或宿主侧 `PermissionError`（如 `require_live_authorization()` 拒绝未授权 live） | 容器内拒绝在工具结果收集点分类计数；宿主侧拒绝在进程日志/退出码观测（`scripts/run_agent_task.py` 未授权退出码 2）。计数规则同 sandbox_violation |

本轮离线实验中三个安全指标必须全为 0；任一非 0 视为工程事故，须先修复再评估，不得计入对比结果。

### 2.4 指标不可变更声明

本节的指标名、来源路径、成功定义在本文件冻结后不得修改（修订规则见 §5）。尤其：不得在看到任何对比结果后调整成功定义、更换聚合分母、增删指标轴。

## 3. Judge 独立性与盲化（冻结）

实现：`src/causalevo/eval/judge.py`；管线侧约束见 `docs/PHASE1_DESIGN.md` §3。

1. **盲化**：`Judge.grade(spec, candidate_workspace)` 的输入只有任务规格与 workspace 路径；管线不向 judge 传 policy 身份（`agent_pipeline.run_agent_tasks` / `pipeline.run_offline` 均如此，manifest notes 固定记录 "judge blinded"）。judge 输出不回流 agent。
2. **sealed 永不给 agent**：`sealed/sealed_tests.py` 与 `reference/` 位于任务目录的 `workspace/` 之外，`WorkspaceFactory` 只复制 `workspace/`（`tests/test_workspace_isolation.py` 守卫）；judge 把 visible/sealed 测试分别复制为 judge 目录内的 `_visible_tests.py` / `_sealed_tests.py`，跑完即删。sealed 断言从不进入 agent 可见面。
3. **judge 侧拷贝**：候选 workspace 被视为只读输入；测试在兄弟目录 `<workspace>.judge` 的独立拷贝上运行，结束（finally）整目录删除；judge 与 agent 不共享可写状态。
4. **源完整性双检**：`WorkspaceFactory.create` 前与 `Judge.grade` 开头各做一次 `spec.verify_hashes()`；agent 跑完后钉死的任务源文件有任何改动即抛 `TaskSpecError`，该任务不得判分。
5. **判分语义**：先 import 探针，语法/导入失败 → `invalid_reason`（非测试失败）；探针或任一测试超时 → `timed_out`；`task_succeeded` 口径见 §2.1。
6. **防泄漏到轨迹**：写入 trace 的 judge 摘要只含 `visible_passed` / `sealed_passed` / visible 失败用例名 / `invalid_reason` / `executor`，**不含 sealed 失败细节**。

## 4. Trace / Manifest 最小模式（冻结）

实现：`src/causalevo/eval/trace.py`。**redacted-by-construction：轨迹不含任何响应正文、原始工具输出或密钥，只有状态、哈希与计数。**

### 4.1 TaskTrace（每任务一条，append+flush 进 `traces.jsonl`）

字段名（冻结）：

- `trace_id`（16 hex）、`task_id`、`split`（train/dev/sealed_test）、`policy_id`、`run_id`
- `states`：八态布尔字典——`api_response_observed` / `tool_executed` / `task_completed` / `visible_tests_passed` / `sealed_tests_passed` / `invalid` / `timeout` / `budget_stop`（`judge.ALL_STATES`）
- `judge`：`visible_passed` / `sealed_passed` / `visible_failures`（用例名）/ `invalid_reason` / `executor`——无 sealed 细节
- `workspace_digest_before` / `workspace_digest_after`：`tree_digest`（对排序后的 (相对路径, 内容) 做 sha256，路径分隔符归一化为 `/`）；双 digest 是重放/重置证据（RISK-3）
- `executor`、`duration_ms`、`created_utc`
- `provider_kind`：`none|fake|replay|live`；`model_invoked`：布尔（fake-agent 管线为 False；真实 Harness agent 循环即使接 fake provider 也为 True——循环确实跑了）
- `agent`（bridge 路径）：`runner` / `finish_reason` / `failure_kind` / `budget_stop_reason` / `final_response_sha16` / `ledger`（快照字段见 §2.2，另含 `elapsed_s`）/ `usage`（可空）/ `events_slim`

### 4.2 RunManifest（`manifest.json`）

字段名（冻结）：`run_id`、`policy_id`、`created_utc`、`split_seed`、`task_count`、`executor_kind`、`config`、`config_sha256`（§1.3 口径）、`notes`（固定声明：离线/fake 产出非模型性能、judge 盲化、sealed 从不进 agent workspace）、`provenance`。

`provenance` 块（`trace.provenance_block()`，缺失值为 None、绝不编造）：`repo_head_sha` / `deepseek_harness_sdk` / `judge_image`（镜像 digest）/ `recorded_utc`。

`report.json` = manifest + summary，供人读；机器消费以 `traces.jsonl` 为准。

## 5. 修订规则（冻结）

1. 本文件自 2026-10-13 起冻结。冻结文本（§1–§5）不得原地修改。
2. 任何变更只能以**新增带日期的章节**（"## 修订 YYYY-MM-DD：……"）形式追加在本文件末尾，且须 Planner 评审批准后方可生效；追加章节须写明被修订条目、新口径、理由与批准记录。
3. **指标后改禁令**：任何指标（§2 的名称、来源、成功定义、聚合口径）在对受影响对比已看到任何结果之后不得变更；先看到结果再改指标的实验产出全部作废。
4. 预算变更除本条外还须满足 §1.3 的三件套（两臂同步 + 新配置哈希 + Planner 评审）。
5. 本协议不冻结实现 bug 修复；修复不得改变冻结口径，否则按修订处理。
