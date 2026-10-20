# CE-DSH-P4-R1.3 — Remediation Evidence（Proxy 凭据隔离 / 账本恢复 / 运行归属）

日期：2026-10-20。Executor：Kimi。本轮**新增 DeepSeek 模型 API 调用 0 次、费用 ¥0**；未运行 `--live`；历史冻结数据（Phase 0–3、Phase 4 2026-10-14 共 312 行）零修改。

对应计划：planner/latest_plan.md（CE-DSH-P4-R1.3）；独立审查：planner/reviews/CE-DSH-P4-R1_2-independent-review.md。

## S1 / P0-A：真实 API Key 不进入 Agent 空间

根因（审查 P0-A）：live 分支 `set_api_key(key)` 把真实 key 放入 `live_pilot._API_KEY_HOLDER`，`run_task_arm` 经 `_current_key()` 传入 `run_task`，`ContainerHarnessRunner` 用 `self.agent_api_key or api_key` 序列化进容器请求 JSON。

修复（结构性，非默认值）：

- `ContainerHarnessRunner.__init__`：`provider_kind="live"` 必须同时显式给出 `provider_endpoint` 与 `agent_api_key`（proxy client token），否则构造期 `ValueError`（`harness_agent.py:268-281`）。
- `run_task`：live（proxied）模式请求 JSON 的 `api_key` 只取构造期 placeholder；调用方传入的 `api_key` 参数（可能持有真实 key）被**刻意忽略**，永不序列化（`harness_agent.py:297-315`）。
- `scripts/run_phase4_pilot.py`：live 分支不再调用 `set_api_key(key)`；真实 key 只用于宿主侧 `query_balance_cny(key)` 与 `ProxyContainer(upstream_api_key=key)`（proxy 容器 env）。`make_live_runner(proxy)` 注入 `agent_api_key=proxy.client_token`。

测试（~~tests/test_secret_isolation.py~~，7 项，真实请求构造/运行路径 + 捕获 subprocess，非对象属性断言）：

> **R1.4 更正**：该文件被 `.gitignore` 的 `*secret*` 保护规则吞没，从未进入远端 tree；R1.4 已改名扩展为 `tests/test_credential_isolation.py`（9 项）并实际提交，见 docs/PHASE4_R1_4_REMEDIATION.md。

- canary 真实 key 作为 `run_task(api_key=CANARY)` 传入：stdin 请求 JSON、docker cmd/env、outcome ledger/events 序列化中 canary 出现 0 次；`request["api_key"] == proxy token`。
- provider 异常路径的 error/ledger/blob 同样 0 次。
- live 构造缺 endpoint/placeholder → `ValueError`。
- `make_live_runner` 工厂接线校验 + 源码守卫（`set_api_key(key)` 不存在）。
- `--live --out` 回归：授权缺失时报 PermissionError，无 NameError/out_dir 未定义（P1-1）。

## S2 / P0-B：账本事件重放与预算恢复

根因（审查 P0-B）：v2 构造函数只统计未结算条数，重启后 `_known_cost=0`、per-task 计数丢失，预算可被重新使用。

修复（`budget_proxy.py` v3 `_replay`）：

- 逐行重放 append-only ledger：按 request_id 校验合法状态转换（∅→RESERVED→SENT→SETTLED/UNKNOWN）；恢复 `_states`、全部 SETTLED 累计费用、每个评估 scope 的请求计数。
- 启动时 RESERVED/SENT 保守转为 UNKNOWN；账本中既有 UNKNOWN 同样阻塞；阻塞期间拒绝一切新请求。
- `reconcile(scope=...)`：显式 scope + 清除列表写入 ledger（可审计）；**绝不清零**历史费用或 scope 计数；账本损坏时拒绝 reconcile（须人工重建）。
- 损坏处理：非法 JSON / 截断行 / 非法转换 / 重复冲突 SETTLED / 负费用 / 畸形 RESERVED → `ledger_corrupt`，fail-closed，且不再向该账本追加任何条目；完全重复的事件按幂等跳过。
- `_persist` flush + fsync（崩溃级持久化）。
- 兼容：R1.2 旧账本的 `task_id` 键按 scope 重放。

测试（tests/test_budget_proxy.py，新增 8 项）：

- 结算 3 次 → 关闭 → 同账本重启：累计费用与 scope 计数完全恢复；超限请求 429 且**上游真实计数 0 增长**。
- 崩溃（SENT 未结算）→ 重启阻塞 → reconcile(scope) → 恢复服务且历史费用/计数不归零；ledger 中留有 scoped reconcile 记录。
- 持久化 UNKNOWN（上游 500）重启后仍阻塞。
- 非法 JSON / 非法转换 / 负费用 / 冲突重复 → corrupt fail-closed；幂等重复不 corrupt。

## S3 / P0-C：唯一评估 scope 与 generation ACK 协议

根因（审查 P0-C/P0-D）：per-task 桶把 6 arms × 2 seeds 混在同一 task_id；宿主先写 control 后删旧 ACK 存在竞态；相同 task_id 重复设置不产生新 ACK 导致超时。

修复：

- 新模块 `src/causalevo/eval/proxy_control.py`：`publish_control`（**先删旧 ACK**，再 tmp+os.replace 原子发布）、`await_ack`（等待同一 generation；发现更新的 generation 视为并发发布者异常）、`apply_control`（proxy 侧：只应用严格更新的 generation 并回显；陈旧/重复/畸形忽略）。
- `ProxyContainer.set_current_scope(scope)`：宿主侧单调 generation + 锁（串行归属）；超时/不匹配 → 抛错 → 拒绝启动 Agent。`__enter__` 末尾执行 bootstrap 握手（证明共享挂载与控制通道可用后才允许 agent 启动）。
- scope 语义：`{experiment_run_id}/{task_id}/{seed}/{arm}`；同一逻辑评估的两次 attempts 归属同一 scope（run_phase4_pilot.py 在 `run_task_arm` 前设置）。`BudgetProxy.set_current_scope` 替代 `set_current_task`（保留兼容别名）。
- 明确串行语义：单 proxy 单活跃 scope；runner 串行执行并用锁保证归属（文档于 proxy_control.py / networks.py docstring）。

测试：

- tests/test_proxy_control.py（8 项，纯离线）：相同 scope 连续 3 次不死锁、A→B→A 快速切换、陈旧/畸形消息忽略、ACK 超时、并发发布者检测、共享挂载缺失、延迟 ACK 接受、锁下串行发布。
- tests/test_proxy_integration_e2e.py：同一 scope 连续设置 3 次后 agent 正常运行（容器级回归）。
- tests/test_budget_proxy.py::test_scopes_of_same_task_are_independent：同 task 不同 arm/seed 计数互不影响。

## S4 / P0-D：Proxy ingress 认证与网络隔离

修复：

- per-run ingress token：`ProxyContainer` 生成 `ce-proxy-<uuid>`，经 env `CE_PROXY_CLIENT_TOKEN` 注入 proxy；runner 把它作为 agent 的 placeholder api_key；DSH runtime 以 Bearer 头发送（容器 E2E 实测可携带）。token 与上游真实 key 无关，且不写入 ledger/日志。proxy_server 无 token 拒绝启动（exit 2）。
- 上游白名单：`ProxyConfig.__post_init__` 校验 host ∈ `allowed_upstream_hosts`（live 默认仅 api.deepseek.com）且必须 https；http 仅宿主可信离线 fake（`allow_insecure_upstream=True` + 显式 host）。ProxyContainer 自动从 upstream URL 推导 env 白名单。agent 无任何指定上游的途径（URL 冻结在配置中，路径固定 `/chat/completions`）。
- 全部入站拒绝/鉴权失败/上游失败/未知 usage 写审计 ledger（不含 key、不含 prompt 原文，仅 body sha16+大小）。

测试：

- tests/test_budget_proxy.py::test_ingress_token_required_when_configured：无 token/错 token → 401 且上游计数 0；正确 token → 200；审计含 2 条 ingress_auth；token 不出现在 ledger。
- tests/test_proxy_integration_e2e.py::test_bridge_sibling_cannot_use_proxy：default-bridge sibling 容器直接向 proxy bridge IP POST → 401；上游 request_count == 0；ledger 审计含 ingress_auth（非仅"端口未发布"的口头隔离）。

## S5 / P0-E：请求与预算上限一致

修复（全部发生在上游 socket 发送之前，且不消耗预算）：

- 路径必须 `/chat/completions`（否则 404）；方法仅 POST（其他 405）；Content-Length 必须存在且 ≤ `worst_case_prompt_tokens` 字节（413）——`prompt_tokens ≤ body bytes`，故界住 body 即保守界住 prompt。
- JSON 可解析且为 chat.completions 形状（400）；`model` 必须等于 `allowed_model`（默认冻结 deepseek-flash，403）；`max_tokens`/`max_completion_tokens` ≤ `worst_case_output_tokens`（403）。
- proxy_server 容器默认 worst-case：prompt 65536 tokens / output 2048 tokens（可通过 env 调整，宿主可信）。

测试：tests/test_budget_proxy.py 新增 4 项（model/max_tokens/body/path+method+json），均以 fake 上游 `call_count == 0` 证明发送前拒绝；`test_upstream_allowlist_and_https_enforced` 覆盖白名单/https。

## P1 补齐

1. `--out` 在初始化前使用：`_resolve_paths(args)` 先于一切 live 设置解析 out_dir/run_id/run_dir；回归测试 test_credential_isolation.py::test_out_dir_resolved_before_live_setup。
2. Fake Provider 真实计数：tape_server 每个 POST 追加 `/tape/requests.jsonl`；`ProviderContainer.request_count()`；E2E cap 测试改为断言上游计数 == 1（不再用 proxy 自身 SENT 行）。
3. Pareto 独立 manifest 钉住：configs/phase3_artifact_manifest.json（pareto_front.json + sweep_results.jsonl 的 expected SHA-256）；adapter 加载前比对，失配即 ValueError（见 S6 小节，由子任务实施）。
4. CEA-v0/v1 多故障场景：scripts/run_phase4_v2_offline.py 重写为 4 场景 × 2 臂（edited_failing / invalid_syntax / no_edit / infra_unknown_cost），edited 由 workspace digest 计算，结果标 `evidence_class=adapter_integration_smoke`。
5. clean_clone_check.py：克隆后校验 `rev-parse HEAD` == `git ls-remote origin main`（或显式参数 SHA），不一致退出 2，无法获取远端退出 3（REMOTE_UNVERIFIED）；保留 no-raw-tasks 断言。
6. status.json：旧 R1.1/R1.2 blockers 移入历史审查记录，当前 blockers 仅列未关闭项。

## 直连状态

配置层 DIRECT 不变（空 ProxyHandler、容器 scrub、NO_PROXY 钉住）；TUN 级仍 `DIRECT_ROUTE_UNVERIFIED`（本轮 0 live 调用，无法实测路由）。

## 测试总览

（最终数字以 planner/executor_report.md 为准）

- tests/test_budget_proxy.py：27 项（含新增 15 项）
- tests/test_credential_isolation.py：9 项（R1.4 改名，原 test_secret_isolation.py 被 gitignore 吞没）
- tests/test_proxy_control.py：8 项
- tests/test_proxy_integration_e2e.py：6 项（Docker 真实参与）
- tests/test_causal_policy_adapter.py / test_phase4_v2_offline.py：S6 子任务结果
- 全量 pytest：见 executor_report.md
