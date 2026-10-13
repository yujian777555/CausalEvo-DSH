# Phase 1 R2 Harness 桥接说明（容器世界 × 协议层 fake provider）

记录日期：2026-10-13。计划：CE-DSH-P1-R2（S1 桥接 / S2 运行时预算 / S3 判分隔离）。
除特别注明外，文中 wire format 与隔离行为声明均来自 2026-10-10 的离线探针实测
（`scripts/probe_fake_provider.py`、`scripts/probe_tool_calls.py`、
`scripts/probe_fs_escape_container.py`、`scripts/smoke_container_bridge.py`）。

**本轮全部为离线工程证据：fake provider 的 usage 是合成值，不构成任何真实计费证据或模型性能声明。**

## 1. 架构

```
host（Windows，运行 pytest / CLI）
│
├─ FakeProvider                     src/causalevo/eval/fake_provider.py
│    ThreadingHTTPServer 绑定 127.0.0.1:<ephemeral port>
│    OpenAI 兼容 POST /chat/completions，SSE 流式响应；零费用、无外部网络
│         ▲ HTTP
│         │ base_url 中 127.0.0.1 改写为 host.docker.internal（bridge 网络）
│
├─ docker run --rm -i --name ceval-agent-<uuid12> --network bridge
│   --memory 768m --memory-swap 768m --cpus 1 --pids-limit 128
│   -v <per-task workspace>:/work        causalevo-dsh-agent:0.1.0
│    └─ /opt/agent_entry.py              docker/dsh-agent/agent_entry.py
│         stdin 收一个任务 JSON（session_id/prompt/model/reasoning_effort/
│         max_tokens/patch_yml/base_url/api_key/request_timeout_s）
│         └─ deepseek-harness-sdk 0.1.5rc1 → 捆绑 runtime 0.1.5-rc.1
│              provider=deepseek-official → http://host.docker.internal:<port>
│              fs 工具（read/write/edit/glob/grep）作用于 /work（唯一挂载，rw）
│         stdout 出 JSONL：{"type":"event","event":...} 逐条流出 +
│         末尾一行 {"type":"final", ok, finish_reason, final_response, events}
│
├─ ContainerHarnessRunner（host 侧）   src/causalevo/eval/harness_agent.py
│    读 stdout 事件流 → RuntimeBudget mid-run 门控；超限/墙钟到期即
│    docker kill <name>（--rm 自动清尸）
│
├─ Judge + DockerExecutor（python:3.11-slim，一次性、--network none 容器）
│    在 workspace 的独立副本上注入 visible+sealed 测试判分；judge 盲化，
│    sealed/reference 从不进入 agent 可见的 /work
│
└─ TraceWriter → results/phase1/r2-offline/<run_id>/
     {traces.jsonl, manifest.json, report.json}
```

镜像构建（`docker/dsh-agent/Dockerfile`）：

- 基础镜像按 digest 钉死：`python@sha256:e88e9763f943ec1834f992a4b51e0f24500486803e8bc534e5767af9ea65f6ce`。
- 完全离线安装：`pip install --no-index --find-links /tmp/wheels deepseek-harness-sdk==0.1.5rc1`，wheels 全部 vendored 于 `docker/dsh-agent/wheels/` 并由同目录 `SHA256SUMS` 记录哈希（含 manylinux runtime-bin wheel）。
- 非 root 用户 `agent` 运行；`DSH_HOME` 为容器内临时目录，任务结束即销毁。
- 任务 profile patch（`configs/dsh_task_patch.yml`）随请求文本注入容器内临时文件：无 shell/web/subagent/skill/上传通道，仅 fs 工具 + fs-sandbox（workspace-write）。

数据流单向：agent 只能读写自己的 /work 副本；judge 只读该副本的独立拷贝；trace 只承载状态/哈希/计数，不回流任何信息给 agent。

## 2. Wire format 实测细节（2026-10-10 探针）

- **请求**：deepseek-official adapter 发 `POST /chat/completions`，`stream: true`；请求体含 `model`、`messages`、`tools`（fs 工具 schema）、`max_tokens` 等。FakeProvider 在 `.requests` 中完整记录每个请求体，`.call_count` 计数，`.tool_results()` 抽取 `role=="tool"` 消息内容供断言。
- **响应**：SSE `data:` 帧序列——首帧 `delta` 携带 `role:"assistant"` + `content`（文本）或 `tool_calls`；末帧 `delta:{}` 携带 `finish_reason`（`stop` 或 `tool_calls`）与 `usage` 块；`data: [DONE]` 收尾。FakeProvider 合成 usage：`prompt_tokens=100+50·i`、`completion_tokens=5+5·len(actions)`、`total_tokens=105+50·i`、`prompt_cache_hit_tokens=64`、`prompt_cache_miss_tokens=36+50·i`（i 为 call_index）。
- **usage 映射**：wire 侧 `prompt_cache_hit_tokens` → 事件 `cacheReadTokens`，`prompt_cache_miss_tokens` → `inputTokens`（未缓存输入，与 cacheRead 互斥），`completion_tokens` → `outputTokens`。`src/causalevo/usage.py` 的别名表同时接受 wire 名与事件名，解析 fail-closed（缺桶即 UsageUnavailable，绝不假设为 0）。
- **工具面**：探针实测请求体 `tools` 恰好五个 function：`read`、`write`、`edit`、`glob`、`grep`（tool-fs / tool-fs-search），无 shell/web/subagent。
- **write 前必须先 read**：fs 工具层要求目标文件在本 session 内先被 `read` 过，否则 `write` 被拒；场景库 `correct_fix`/`wrong_fix` 因此按 read → write → final 编排。
- **usage 事件与 HTTP 请求 1:1**：带 usage 的 `assistant/message` / `assistant/attempt` 事件与 FakeProvider 端记录的 HTTP 请求一一对应（探针实测 6 个 usage 事件 ↔ 6 个 HTTP 请求）。这是 `usage.py` 判重原则的证据来源：不同事件 `seq` 即不同计费请求，**usage 数值不得用于判同**；无 id 且 usage 与同 (turn,step) 已提交 message 相等的 attempt 属身份不明 → fail-closed。

## 3. fake 层位置的准确声明

FakeProvider 位于 **provider 协议层（transport），不是 SDK 内部 patch**：

- SDK（deepseek-harness-sdk 0.1.5rc1）与 runtime 二进制（0.1.5-rc.1）未打任何代码 patch，未 mock/monkey-patch 任何内部函数；唯一改动是配置项 `base_url` 指向 `http://127.0.0.1:<port>`（容器世界内经 `host.docker.internal`），`api_key` 为占位串 `sk-fake-offline-no-cost`。
- 因此以下组件全部真实经过：SDK → stdio JSON-RPC → runtime 进程 → Cordis 插件树 → deepseek-official adapter → HTTP client → SSE 解析 → 工具分发 → fs 工具执行 → session 事件流。未经过的只有真实 DeepSeek 服务端。
- 这满足 CE-DSH-P1-R2 S1 对「Fake LLM Adapter 在 Harness protocol 层」的要求；R1 的 `pipeline.run_offline`（FakeAgent 直接改文件）不算该 gate，是另一类工程证据，两者不混称。

## 4. AgentRunOutcome 字段表

`ContainerHarnessRunner.run_task(...) -> AgentRunOutcome`（`harness_agent.py`）：

| 字段 | 类型 | 含义 |
|---|---|---|
| `task_id` | str | 任务 id（对应 benchmarks/tasks 条目） |
| `policy_id` | str | `B0-fixed-harness` / `B1-self-reflection-fixed-budget` |
| `finish_reason` | str \| None | runtime 报告的结束原因（如 `completed`）；异常路径为 None |
| `final_response_sha16` | str \| None | 最终回答文本 sha256 前 16 hex；原文不落盘 |
| `failure_kind` | str | `none` / `provider_error` / `timeout` / `budget_stop` / `transport` / `protocol` / `invalid` |
| `budget_stop_reason` | str \| None | `BudgetStop.reason`；非预算异常路径承载错误摘要 |
| `usage` | UsageRecord \| None | 全部独立请求聚合的 settled usage（`extract_settled_usage`）；无法确定则为 None（fail-closed，不当 0） |
| `ledger` | dict | `budget.snapshot()`：`provider_attempts`、`tool_attempts`、`known_input_tokens`、`cache_read_tokens`、`output_tokens`、`known_cost_cny`、`unknown_spend_attempts`、`elapsed_s` |
| `events_slim` | list[dict] | 脱敏事件图：`seq`/`type`/`turn`/`step`/usage 数字/工具名 + 每事件 sha16；**无文本体** |
| `duration_ms` | int | 单次任务墙钟耗时 |
| `runner` | str | `container`（`host` 仅存于 HostHarnessRunner，探针/调试专用） |
| `provider_kind` | str | `fake` / `live` |
| `model_invoked` | bool | 真实 Harness agent loop 是否执行（fake provider 下亦为 True：runtime 真实运行；区别于「是否有真实 API 响应」，后者由 trace 状态 `api_response_observed` 表达且仅 live 置真） |

## 5. RuntimeBudget 实时门控

`src/causalevo/eval/runtime_budget.py` 是活账本，不是静态 dataclass：

- **预留（请求前）**：`before_provider_request(reserved_cost_cny)` 先查墙钟，再查 `provider_attempts+1 > max_provider_calls`（早失败），再查 `known_cost_cny + reserved_cost_cny + 新预留 > max_cost_cny`；通过后预留额**跨请求累计**，作为保守上界。
- **结算（响应后）**：`after_provider_request(usage, price_tier, usd_cny)`：`provider_attempts += 1`；`usage=None` → `unknown_spend_attempts += 1` 并立即 `BudgetStop("unknown_cost ...")`（fail-closed，失败尝试绝不当免费）；否则累加输入（uncached+cache_write）/cache_read/output 桶与 `known_cost_cny`（`pricing.cost_for_usage`），超 output cap 或 cost cap 即 `BudgetStop`。
- **多步累计**：运行结束由 `_settle_budget` 对 `extract_request_usages(events)` 返回的**每个独立 provider 请求**逐一结算——工具循环产生的多步请求、失败但带 usage 的 attempt 全部计入同一 envelope。
- **工具门控**：`before_tool_call(name)` 先查墙钟，`tool_attempts+1 > max_tool_calls` 即 `BudgetStop`，否则计数。
- **墙钟 watchdog（容器世界）**：reader 线程 + queue 与主循环解耦，`deadline = start + wall_time_s`，`queue.get(timeout=min(remaining, 0.5))` 使墙钟在 provider 挂起、无任何输出流时仍能触发；超时（`_WallClockExpired`）或 `BudgetStop` 均执行 `docker kill <name>`——**超支在边界处硬停，而非事后对账发现**。
- **mid-run 语义**：容器内 mid-run 执行为**事件流反应式**——每收到一条 `tool/call` 事件即计数/即停；请求次数与成本上限在起点预留检查与结束逐请求结算两处强制；跨请求预留为保守上界。

## 6. 场景库（scenarios.py）

`src/causalevo/eval/scenarios.py`：`SCENARIOS` 七个场景，每个是 `TaskSpec -> script(messages, call_index) -> actions` 工厂，驱动真实 agent loop：

| 场景 | 脚本行为 | 验证的通路/故障类型 |
|---|---|---|
| `noop` | 直接文本作答 | 端到端基线通路（无工具调用；judge 面对未修改的 workspace） |
| `correct_fix` | read → write(参考修复) → final | 正常修复链路 + judge 判对能力（工程证据，非性能） |
| `wrong_fix` | read → write(`return None` stub) → final | judge 判错路径（sealed 失败被正确归类） |
| `bad_tool_call` | 调用 `definitely_not_a_tool` → 文本收尾 | 未知工具名的分发/错误回报路径 |
| `provider_error` | HTTP 500 + error payload | `failure_kind=provider_error` 归类 |
| `provider_timeout` | `("sleep", 30)` 挂起响应后正常作答 | provider 挂起路径；测试中以更小墙钟预算触发 `timeout` 分支与 watchdog kill |
| `tool_over_budget` | 每步 `glob(**/*.py)` 无限循环 | `max_tool_calls` mid-run 触发 `budget_stop` + `docker kill` |

动作原语：`("text", str)` / `("tool_call", name, args)` / `("error", status, payload)` / `("sleep", seconds)`。

## 7. B0/B1 预算平价如何在运行时落地

- **静态层**：`policy.py` 中 B0/B1 共享同一个 frozen `Budget(max_provider_calls=2, max_total_output_tokens=2048, max_tool_calls=20, wall_time_s=300)`；`check_budget_parity` 由测试锁定，B1 的 reflection + re-attempt 必须从同一 envelope 扣除（`max_provider_calls=2` 正好容纳初解 + 一次反思重试），任何预算变更须同口径改两者。
- **运行时层**：`run_agent_task.py` 的 `budget_factory()` 为**每个任务**从 `policy.budget` 新建 `RuntimeBudget`（四项上限逐字段拷贝）；`harness_agent.py` 对两个 policy 走完全相同的预留/结算/门控代码路径，无 policy 分支；每任务的 `ledger` 快照写入 `trace.agent.ledger`，与 `run_id`/`policy_id` 一起可审计、可复算。

## 8. live 授权门（CE_DSH_LIVE_AUTH）

- `require_live_authorization()`：缺 `DEEPSEEK_API_KEY` → `PermissionError`；`CE_DSH_LIVE_AUTH != "phase1-pilot"`（Planner 一次性授权旗标）→ `PermissionError`，**在任何 socket 打开之前拒绝**。两个条件缺一不可。
- `scripts/run_agent_task.py --live`：先过授权门；R2 不排期 live，即使授权通过也仅打印提示并 `return 2`。
- trace 诚信约定：`provider_kind=fake|live`；`api_response_observed` 仅在 live 时置真（fake 运行恒为 False）；fake 运行的 `api_key` 为固定占位串，无密钥材料落盘。

## 9. 复现命令

```bash
# 镜像（本机已构建可跳过；构建本身完全离线，wheels 已 vendored 并有 SHA256SUMS）
docker build -t causalevo-dsh-agent:0.1.0 docker/dsh-agent

# 测试（含 fake provider wire 级、预算门控、容器隔离等）
.venv/Scripts/python.exe -m pytest tests/ -q
.venv/Scripts/python.exe -m pytest tests/test_fake_provider.py -q

# 端到端（fake provider，离线零费用；默认输出 results/phase1/r2-offline/）
.venv/Scripts/python.exe scripts/run_agent_task.py --fake --scenario noop
.venv/Scripts/python.exe scripts/run_agent_task.py --fake --scenario correct_fix --tasks 3
.venv/Scripts/python.exe scripts/run_agent_task.py --fake --scenario tool_over_budget \
    --policy B1-self-reflection-fixed-budget

# live（默认被拒绝：无授权旗标即 PermissionError，且 R2 不排期 live）
.venv/Scripts/python.exe scripts/run_agent_task.py --live
```

## 10. 明确限制

1. **fake usage 是合成值**（`prompt_tokens=100+50·i` 等固定公式），只验证记账、门控与事件解析通路；**不是真实计费证据，不构成任何模型性能或成本结论**。Fake-provider 运行均为工程证据。
2. 容器内 mid-run 预算执行为**事件流反应式**：收到事件即计数、超限即停；provider 请求次数与成本上限在起点预留检查与结束后的逐请求结算处强制，**跨请求预留为保守上界**；无事件流出期间由墙钟 watchdog（0.5s 粒度轮询 deadline）+ `docker kill` 兜底。
3. `HostHarnessRunner` **不是隔离边界**（2026-10-10 实测：fs-sandbox 限写不限读，host canary 被原样读出），仅限探针/调试；任务执行只允许容器世界。容器世界已实测反向结论：宿主绝对路径读取、`../` 穿越、全盘 grep 均读不到 canary，越界写入被拒。
4. agent 容器为 `--network bridge`（连通 `host.docker.internal` 上的 fake provider 所需）；模型面 web 工具已被 profile patch 禁用，但容器网络命名空间本身未断网——断网隔离属于 judge 容器（`--network none`），两者不混称。
5. FakeProvider 的 `error`/`sleep` 是脚本注入故障，用于验证失败归类与超时路径，不代表真实 provider 的故障分布。
