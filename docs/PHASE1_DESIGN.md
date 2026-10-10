# Phase 1 架构设计（离线工程管线）

日期：2026-10-10。对应计划 CE-DSH-P1-R1（`planner/latest_plan.md` P1.2–P1.5）。

**范围声明：Phase 1 本轮只交付离线、零成本、零真实 API 调用的工程管线。所有执行均由确定性 FakeAgent（noop/break/oracle）驱动，其产出是管线证据，不是、也不得被引用为模型性能。外部基准（SWE-bench Verified 等）仅完成元数据审计（`docs/PHASE1_BENCHMARK_DECISION.md`、`benchmarks/registry.json`），未下载、未运行。live 预算 = 0 CNY，需用户明确授权后由 Planner 另发计划。**

实现位于 `src/causalevo/eval/`（task_spec / workspace_factory / executor / judge / trace / metrics / policy / pipeline），配置位于 `configs/phase1_b0.yaml`、`configs/phase1_b1.yaml`、`configs/dsh_task_patch.yml`，任务位于 `benchmarks/tasks/`（26 个 microtask，train 13 / dev 7 / sealed_test 6，split seed 20261010；计划要求 ≥24，实际生成 26，以 `benchmarks/registry.json` 与生成器 assert 为准）。

## 1. 组件图与数据流

```
configs/phase1_b0.yaml / phase1_b1.yaml          benchmarks/tasks/<task_id>/
        │  （离线镜像 policy.py 中 B0/B1 定义）      ├─ task.json（元数据 + 4 个文件 sha256）
        ▼                                          ├─ workspace/solution.py（ buggy，agent 唯一可见）
run_offline(specs, policy, judge, executor, ...)   ├─ visible_tests.py（judge 侧注入）
  │                                                ├─ sealed/sealed_tests.py（judge 侧注入，物理隔离）
  │  对每个 TaskSpec：                               └─ reference/solution_fixed.py（仅 oracle 模式用）
  │
  ├─ WorkspaceFactory.create(spec, run_id)
  │     先 spec.verify_hashes() 校验钉死的源文件哈希，
  │     再把 workspace/ 全新复制到 <base>/<run_id>--<task_id>/（已存在则先整目录删除），
  │     记录 tree_digest 作为 digest_at_open。
  │
  ├─ FakeAgent.act(spec, ws.root, policy)          ← 只写 workspace 内文件
  │     noop=不修改 / break=写入语法错误文件 / oracle=复制 reference 修复（仅工程验证）
  │
  ├─ Judge.grade(spec, ws.root)                    ← 不接收 policy（盲化）
  │     复制候选 workspace 到兄弟目录 *.judge，注入 visible+sealed 测试，
  │     经 executor 运行 import 探针 + 两套测试，判分后删除 judge 目录。
  │
  ├─ TraceWriter.write_trace(TaskTrace)            → traces.jsonl（逐条 append+flush）
  │
  └─ summarize_traces(traces)                      → report.json（manifest + summary）
        TraceWriter.write_manifest(RunManifest)    → manifest.json
        收尾：writer.close()；factory.destroy_all() 删除全部 workspace
```

数据流单向：agent 只能改自己的 workspace 副本；judge 只读该副本（在独立拷贝上跑测试）；trace 只承载状态/哈希/计数；metrics 只做计数聚合。judge 不回流任何信息给 agent，sealed 测试从不进入 agent 可见目录。

关键入口签名（与代码一致）：

- `task_spec.load_all_tasks(tasks_dir, verify=True) -> list[TaskSpec]`：加载并逐文件校验 sha256；split 必须是 train/dev/sealed_test。
- `pipeline.run_offline(specs, policy, judge, executor, out_dir, fake_mode="noop", split_seed=0, run_id=None, config=None) -> {run_id, summary, run_dir}`：调度 tasks × policy，判分、写 trace、出汇总。默认 `run_id = "<policy_id>-<UTC %Y%m%dT%H%M%SZ>"`，B0/B1 各有独立 run 目录。
- `executor.default_executor(prefer_docker=True)`：docker 可用 → `DockerExecutor`（镜像 `python:3.11-slim`），否则 → `LocalTrustedExecutor`。

## 2. 安全边界

### 2.1 双层 executor：非可信内容只允许走 Docker

`DockerExecutor` 是**唯一允许运行非可信（模型生成）内容的路径**。每条命令一个一次性容器，精确参数（`executor.py`）：

| 隔离维度 | 机制 |
|---|---|
| 网络 | `--network none` |
| 根文件系统 | `--read-only` |
| 任务目录 | `-v <workdir>:/work:ro`（只读挂载当次任务目录，不挂其他路径） |
| 内存 | `--memory 256m --memory-swap 256m` |
| CPU / 进程数 | `--cpus 1` / `--pids-limit 64` |
| 身份 | `--user 65534:65534`（非 root） |
| 生命周期 | `--rm` + 唯一名 `ceval-<12hex>`，超时先 `docker kill <name>` 硬杀再收割 |
| 确定性 | 固定 `PYTHONDONTWRITEBYTECODE=1`、`PYTHONHASHSEED=0` |
| 超时 | 硬 wall-clock 超时；超时后 `exit_code=None`、`timed_out=True` |
| 输出 | stdout/stderr 仅保留尾部 8000 字符（且不进 trace，见 §6） |

`LocalTrustedExecutor` 是宿主机子进程，环境最小化（仅 `PATH`、`SYSTEMROOT`、`PYTHONDONTWRITEBYTECODE`、`PYTHONHASHSEED`，不继承任何密钥），硬超时。**它仅限仓库内置可信内容（fake policy 动作、reference 修复、测试脚本）**，模型生成代码不得走该路径。诚实说明：这一边界目前由评审纪律保证而非 OS 强制（见 `executor.py` 模块 docstring）；Docker 不可用时，fake/replay 路径可继续工作，但真实模型代码执行必须标记 BLOCKED，不退化为宿主机执行（计划 P1.2）。docker 路径由 `tests/test_executor_isolation.py` 做对抗性验证（断网、读不到宿主文件、挂载只读、不继承密钥、超时 kill 不留容器、内存上限）。

### 2.2 DSH 任务 profile（最小权限，供未来 live pilot）

`configs/dsh_task_patch.yml` 是**未来 live pilot 专用**的 harness profile patch，离线 pipeline 不使用它。与 Phase 0 的 `dsh_bench_patch.yml`（禁用一切工具，纯计量基准）不同，任务执行需要文件编辑，因此采取最小权限：

- **禁用**：shell 系列（tool-pwsh / tool-bash / tool-jobs / pwsh-sandbox / bash-sandbox）、web 系列（tool-web / web / web-search-deepseek / web-fetch-http）、skills/commands/goals/plans、subagent/workflow 系列、历史改写（compaction-basic、session-checkpoint-policy）、上传通道（session-telemetry-otel、session-log-deepseek）及一批不需要的辅助插件。
- **保留**：tool-fs、tool-fs-search、fs-sandbox、sandbox-policy（workspace-write，由 runner 环境钉死 `DSH_PERMISSION_MODE`）、approval（policy=ask）、timeout-policy。模型只能通过 workspace 内的文件系统工具改文件；候选代码的执行只发生在 judge 侧 Docker 容器内，绝不经过宿主 shell。
- **subprocess 保留**：dsh-tool-fs-search 需要它启动捆绑的 ripgrep sidecar；该服务不向模型注册任何工具。
- **permission 插件被禁用**：permission-presets 等待只有 shell 工具插件才提供的 "shell" 服务，shell 工具已禁用则它永远无法激活，故显式关闭（approval 本体保留）。只设环境变量或写 prompt「不要访问」不构成隔离，显式插件清单才是机制。

## 3. Judge 独立性与盲化、sealed tests 物理隔离

- **盲化**：`Judge.grade(spec, candidate_workspace)` 的输入只有任务规格与 workspace 路径；`run_offline` 不向 judge 传 policy（代码注释与 manifest notes 均记录 "judge receives no policy identity (blinded)"）。数据划分与判分对策略不可见。
- **源完整性双检**：`WorkspaceFactory.create` 前与 `Judge.grade` 开头各做一次 `spec.verify_hashes()`——agent 跑完后钉死的任务源文件（ buggy 原件、visible/sealed 测试、reference）有任何改动即抛 `TaskSpecError`。
- **judge 侧拷贝**：候选 workspace 被视为只读输入；测试在兄弟目录 `<workspace>.judge` 的拷贝上运行，结束（finally）整目录删除。judge 与 agent 不共享可写状态。
- **sealed 物理隔离**：`sealed/sealed_tests.py` 与 `reference/` 位于 `workspace/` 之外，`WorkspaceFactory` 只复制 `workspace/`（`tests/test_workspace_isolation.py::test_workspace_excludes_sealed_tests_and_reference` 守卫）。judge 把 visible/sealed 测试分别以 `_visible_tests.py` / `_sealed_tests.py` 注入 judge 目录，跑完即删。sealed 断言从不进入 agent 可见面。
- **判分语义**：先做 import 探针（`python -c "import solution"`），语法/导入失败 → `invalid_reason`（不是测试失败）；探针或任一测试超时 → `timed_out`。`task_succeeded = visible_passed and sealed_passed and not invalid_reason and not timed_out`。finish_reason=completed、输出格式正确、模型自称修好都不算任务成功。
- **防泄漏到轨迹**：写入 trace 的 judge 摘要只含 visible 失败用例名与 invalid_reason，**不含 sealed 失败细节**，避免 sealed 断言信息随轨迹回流后续会话。

## 4. 状态机（8 态）

`judge.ALL_STATES` 定义、`run_offline` 每任务初始化为全 False 后按事实置位：

| 状态 | 含义 | 置位方 |
|---|---|---|
| `api_response_observed` | 观测到一次（fake/未来 live 的）模型响应 | agent |
| `tool_executed` | agent 对 workspace 执行了文件修改（noop 下为 False） | agent |
| `task_completed` | agent 正常返回（无异常）。**不等于任务成功** | pipeline |
| `visible_tests_passed` | visible 测试全部通过 | judge |
| `sealed_tests_passed` | sealed 测试全部通过 | judge |
| `invalid` | agent 异常，或 judge 判 invalid（入口缺失 / import 失败） | pipeline + judge |
| `timeout` | judge 侧任一执行（探针/测试）超时 | judge |
| `budget_stop` | 预算截断保留位；当前离线 fake 管线不置位（预算为静态定义，运行时计量截断属 live 阶段） | （保留） |

指标口径随之分层（`metrics.summarize_traces`）：`requested`（任务总数）、`executed`（task_completed）、`scored`（未 budget_stop）、`visible_tests_passed` / `sealed_tests_passed` / `task_succeeded`（双侧均过）、`invalid`、`timeouts`、`success_rate_over_executed`（executed=0 时为 None）。summary 固定附注 "offline pipeline validation; fake-policy outcomes are NOT model performance"。执行成功与任务通过是两个不同的数。

## 5. B0/B1 预算平价设计

`policy.py`：`Budget(max_provider_calls=2, max_total_output_tokens=2048, max_tool_calls=20, wall_time_s=300)`。B0 与 B1 使用**完全相同的 Budget envelope**，差异只在决策策略：

| | B0-fixed-harness | B1-self-reflection-fixed-budget |
|---|---|---|
| `allow_reflection` | False | True（一次结构化复盘 + 一次再尝试） |
| `max_attempts_per_task` | 1 | 2 |
| `budget` | 同一 envelope | 同一 envelope |
| `persistent_updates` | False（遇失败不持久改 Prompt/Skill/Tool） | False（不跨任务改 Agent 组件） |

公平性规则：B1 的复盘/再尝试从同一个池子里扣，不存在"多想一次自然更贵"。`check_budget_parity(a, b)` 对 budget 不等或任一 persistent_updates=True 抛 `ValueError`；平价由测试强制而非约定（`tests/test_policies.py`：逐字段相等、篡改预算即抛错、两个 YAML 配置与 policy 对象一致）。`configs/phase1_b0.yaml` / `phase1_b1.yaml` 是这两个对象的离线镜像（execution.mode=offline、executor=docker、fake_agent_mode=noop、splits=[train, dev, sealed_test]）。诚实说明：本轮预算是静态定义与平价门，离线管线不做运行时 token/费用计量；运行时预算 gate 属 live 阶段（见 §7 RISK-6）。

## 6. Trace / Manifest 模式

**redacted-by-construction：轨迹不含任何响应正文、原始工具输出或密钥，只有状态、哈希与计数。**

- `TaskTrace`（每任务一条，append+flush 进 `traces.jsonl`）：`trace_id`（16 hex）、`task_id`、`split`、`policy_id`、`run_id`、`states`（§4 八态）、`judge`（visible_passed / sealed_passed / visible_failures 名称 / invalid_reason / executor——无 sealed 细节）、`workspace_digest_before` / `workspace_digest_after`（`tree_digest`：对排序后的 (相对路径, 内容) 做 sha256，路径分隔符归一化为 `/`）、`executor`、`duration_ms`、`created_utc`。
- `RunManifest`（`manifest.json`）：`run_id`、`policy_id`、`created_utc`、`split_seed`、`task_count`、`executor_kind`、`config`、`config_sha256`（配置 json sort_keys 后 sha256 前 16 位）、`notes`（固定声明：offline fake agent 非模型性能、judge 盲化、sealed 从不进 agent workspace）。
- `report.json` = manifest + summary，供人读；机器消费以 traces.jsonl 为准。
- workspace 前后双 digest 是重放/重置证据（RISK-3）：证明每任务从 pristine 态全新开始，agent 改动范围可见。
- 已知限制（沿用 Phase 0 口径）：live 阶段还需在 manifest 中补 provider/model、SDK 版本、patch hash、镜像 digest、repo commit（P1.2 要求），本轮离线无这些字段的数据来源。

## 7. P1.5 遗留风险门映射（RISK-1..6）

| 风险 | 状态 | 机制 / 未决项 |
|---|---|---|
| RISK-1 attempt 身份不明导致重复计量 | **未决（live）** | 本轮离线零 API 调用，不触发；fake 管线无自动重试。Phase 0 已落地 attempt 用量解析 fail-closed（`tests/test_usage_attempt_events.py`）。live 多步/重试前必须先过专门失败注入测试 + Planner 复审。 |
| RISK-2 多步 attempt 计量混淆 | **未决（live）** | 离线无计费请求。状态机把 `api_response_observed` / `tool_executed` / `task_completed` 分开，为未来"每条 provider 计费请求唯一计量、未计量不为 0"留位；live pilot 前复审。 |
| RISK-3 重放须真正重建环境 | **已落地（离线层）** | 每任务从哈希校验过的 pristine 源**全新复制**（已存在先整目录删除）；`Workspace.reset` 全量重建；前后 `tree_digest` 入 trace；容器一次性 `--rm` + 唯一名 + 超时硬 kill。测试：`test_reset_restores_pristine_digest`、`test_two_workspaces_for_same_task_are_independent`。live 阶段容器级重建在 task profile pilot 时另行验证。 |
| RISK-4 API 观测成功 ≠ 任务成功 | **部分落地** | 八态分离；`task_succeeded` 仅由 judge 双侧测试决定；`config_sha256` 入 manifest。未决：live 的模型别名漂移、推理参数与 max-tokens 截断记录（Phase 0 已示范披露 41/100 max-tokens）。 |
| RISK-5 污染 / 隐性测试泄漏 | **已落地（microtask 层）** | sealed/reference 物理隔离于 workspace 外、仅 judge 侧注入且用后删除；trace 不含 sealed 失败细节；split seed 20261010 一次固定、registry.json 钉死全部文件哈希；生成器 assert 函数名与 bug 类各 26 个全唯一（去重审计）。外部基准污染风险在 registry.json 逐条标 `contamination_risk` 与 NOT_VERIFIED；sealed split 纪律：只评估、绝不用于调参。 |
| RISK-6 实时预算 gate | **已落地（本轮）** | 本轮 live 预算 = 0；`pipeline.py` 不存在任何触网或读 API key 的代码路径；B0/B1 envelope 静态锁定 + parity 测试。任何预算提升必须用户明确授权 + Planner 新计划。 |

## 8. 复现命令（Windows，Git Bash；Linux/WSL 同理）

```bash
# 1) 虚拟环境与锁定依赖
py -3.10 -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements-lock.txt

# 2) 确定性重建 26 个 microtask（seed 20261010；同 seed 重建字节一致，
#    registry.json 钉死全部文件哈希，测试强制一致）
.venv/Scripts/python.exe scripts/generate_microtasks.py

# 3) 全量离线测试（无需密钥、无需网络）
.venv/Scripts/python.exe -m pytest tests/ -q

# 4) 离线 pipeline（默认 docker executor，需本机已有 python:3.11-slim 镜像；
#    docker 不可用则回落 local-trusted —— 仅限 fake/replay 可信内容）
PYTHONPATH=src .venv/Scripts/python.exe -c "
from pathlib import Path
from causalevo.eval.task_spec import load_all_tasks
from causalevo.eval.executor import default_executor
from causalevo.eval.judge import Judge
from causalevo.eval.policy import B0, B1, check_budget_parity
from causalevo.eval.pipeline import run_offline

check_budget_parity(B0, B1)                      # 平价门：不等即抛 ValueError
specs = load_all_tasks(Path('benchmarks/tasks')) # 26 tasks，逐文件校验哈希
ex = default_executor()
judge = Judge(ex)
for policy in (B0, B1):
    r = run_offline(specs, policy, judge, ex,
                    Path('results/phase1/offline'),
                    fake_mode='noop', split_seed=20261010)
    print(r['run_id'], r['summary'])
"
```

预期口径（fake_mode='noop'）：requested=26、executed=26、`task_succeeded=0`——noop agent 不修任何 bug，0 通过是**正确**报告；`fake_mode='oracle'` 仅用于工程验证 judge 能判通过，同样不得引用为模型结果。`fake_mode='break'` 应使全部任务 invalid。

## 9. 本轮明确不做

- 不调用任何付费/真实 API（预算 0 CNY，P1-G7）；`dsh_task_patch.yml` 仅为未来 pilot 准备。
- 不报告任何模型成功率；外部基准无下载、无运行、无数字。
- 不实现 CausalEvo 自进化、失败机制诊断（Phase 2 内容）；B0/B1 只有离线定义与 fake 验证。
- 不修改 Phase 0 冻结产物（`results/phase0/` 只读）。
