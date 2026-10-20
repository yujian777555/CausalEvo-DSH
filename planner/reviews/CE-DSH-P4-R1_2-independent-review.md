# CE-DSH-P4-R1.2 — GPT Planner 独立源码复审

- 审核远端 HEAD：be14f380433e6b08788e8dc47950a3a90c640b72
- 结论：**CHANGES_REQUESTED / PARTIAL**，不批准 live/付费 pilot。
- 审查方法：GitHub Connector 读取最新 main 的源码、测试、状态文件与报告；未在 Executor 的 Windows/Docker 主机重新运行 447 项测试，也未发出真实 DeepSeek 请求。
- 费用：本次 Planner 未调用模型 API；Executor 报告本轮新增模型 API 调用 0 次、¥0。

## 已确认的进展

1. auditable_tasks.jsonl 已提交；src/causalevo/eval/auditable.py 为 312 行投影提供 schema/hash/唯一性检查。统计脚本默认读取去敏投影，clean-clone 脚本和离线结果已添加。
2. run_phase4_pilot.py live 分支现在创建 ProxyContainer 并传入 endpoint；ContainerHarnessRunner 在 live endpoint 缺失时拒绝运行，已消除显式 direct-provider fallback。
3. 新的 run_phase4_v2_offline.py 调用了 CausalPolicyAdapter.cea_v0/cea_v1，这是离线适配器集成 smoke test，不是算法优越性或真实模型效果证据。
4. 历史 Phase 0–3 及 2026-10-14 的 312 行真实实验数据未在本次差异中被改写；历史 B5 对 B1 无优势证据的结论必须保留。

## P0 — 必须修复

### P0-A：真实 DeepSeek API Key 会进入 Agent 容器请求

源码：
- scripts/run_phase4_pilot.py:87-95
- src/causalevo/eval/live_pilot.py:188-198
- src/causalevo/eval/harness_agent.py:297-306

live 分支执行 set_api_key(key)，而 make_runner() 没有设置 agent_api_key。随后 run_task_arm() 传入 api_key=_current_key()；容器请求使用 self.agent_api_key or api_key，所以真实 key 被写入 stdin JSON 并交给 Agent runtime。这违反了“真实 key 只在 Proxy”的安全承诺。

验收要求：真实 key 仅用于宿主侧必要的余额查询和可信 Proxy 配置；Agent 请求只能携带无权限占位值。新增请求序列化/容器入口测试，断言真实 key 不在请求 JSON、容器环境、trace、异常和日志中。

### P0-B：Proxy 重启后已结算费用和 per-task 计数被重置

源码：src/causalevo/eval/budget_proxy.py:61-95

构造函数扫描历史 ledger 只计算当前未结算状态数，没有恢复 _known_cost、_per_task 和 self._states。若旧 ledger 只有 SETTLED 项，重启后 _stopped=False、_known_cost=0、per-task count 为空，预算可以被重新使用；发生未结算项并人工 reconcile 后，历史已知费用仍未恢复。

验收要求：从完整事件日志重放并重建每个 request_id 的最终状态、已结算费用、每个 scope 的调用数和保留额度；校验状态转换、重复事件、负费用和账本损坏；不一致或无法重建时 fail-closed。覆盖“成功结算多次→重启→额度不归零”的回归测试。若承诺断电级 durability，预留写入后还需适当 fsync。

### P0-C：控制通道确认存在竞态，重复 task_id 可能卡住

源码：
- src/causalevo/eval/networks.py:106-124
- scripts/proxy_server.py:36-50

宿主先写 control.json 后删除旧 control_ack.json，存在删除刚生成的新 ACK 的竞态。另一个确定性问题是控制循环只在 data != last 时发 ACK；连续两次相同 task_id 的控制消息不产生新 ACK，而宿主每次都等待新 ACK。

验收要求：引入单调递增的 generation/request ID，先清理旧 ACK，再原子发布新控制消息；ACK 必须匹配同一 generation。连续相同任务、重试、快速切换、旧 ACK 延迟、并发控制都必须有测试。

### P0-D：per-task 限额按 benchmark task_id 聚合了不同实验行

源码：scripts/run_phase4_pilot.py:66-72 和 src/causalevo/eval/budget_proxy.py:119-139。

当前只调用 proxy.set_current_task(spec.task_id)。同一个 benchmark task 会在 6 个 arm、2 个 seed 中重复使用，而 Proxy 的 max_requests_per_task=8 将这些独立评估行累计到同一桶；这可能导致正式 pilot 在同一任务的后续 arm/seed 被错误拒绝，并且账本无法准确归属 run。

验收要求：为每条逻辑评估建立唯一且稳定的 scope ID，至少区分 experiment_run_id/task_id/seed/arm；重试属于该评估行并单独记录 attempt。不要将多个 arm/seed 混进一个 task cap，也不要通过扩大 cap 隐藏错误归属。

### P0-E：双网卡 Proxy 暴露在 default bridge，入口没有客户端鉴权

源码：
- src/causalevo/eval/networks.py:71-90
- scripts/proxy_server.py:65
- src/causalevo/eval/budget_proxy.py:161-194

Proxy 连接 internal ceval-net 与默认 bridge，服务绑定 0.0.0.0:8081。HTTP Handler 没有验证来访客户端身份；它会把请求体转发到可信上游并注入真实 API key。因此，其他能够连接默认 bridge 的容器可能绕过预期 Agent 身份，消耗预算或调用账户。

验收要求：Proxy ingress 必须限制在授权 Agent/网络范围内，并加入与上游 API key 不同的代理客户端认证或等效网络隔离。验证 default-bridge sibling 无法请求 Proxy；授权 Agent 可以访问。不能只以“端口未发布到宿主机”作为隔离证明。

### P0-F：固定 worst-case 预算未对实际请求体强制约束

源码：src/causalevo/eval/budget_proxy.py:114-139,218-230

Proxy 用固定 worst_case_prompt_tokens/output_tokens 预留，但未验证实际 JSON 请求的 model、max_tokens/max_completion_tokens、prompt 大小或 endpoint path 是否落在这些上限内。入口无客户端鉴权时，任意可访问者还可能指定不同模型或更大的请求。此时“预留上限”未必覆盖真实账单。

验收要求：在转发前解析并验证请求体，固定允许的 DeepSeek 主机和模型，限制输出 token，并对输入 token/大小实施保守上限；无法保证上限时拒绝发送。验证所有拒绝发生在上游收到请求之前。

## P1 — 必须补齐

1. **--out live 路径使用未初始化的 out_dir**：scripts/run_phase4_pilot.py:93-106 在初始化 out_dir 之前于条件真分支读取它。先解析输出目录，再创建 Proxy，增加 --out 入口的离线 mock 测试。
2. **Proxy cap E2E 的上游调用断言不直接观察上游**：tests/test_proxy_integration_e2e.py:96-100 读取的是 Proxy ledger 中的 SENT 数量，并非 fake upstream 自身请求计数。请增加 provider-side request counter，并核对上游确实只收到一次。
3. **CEA-v1 的 Pareto SHA 尚未与独立固定 manifest 比对**：adapter.py:74-95 读取当前文件后计算 hash，再把同一个 hash 保存为 provenance；_front_members() 只验证加载后是否变化。这不能证明加载时文件等于预注册的可信工件。用独立、提交且冻结的 manifest 提供 expected SHA。
4. **B4-v2/B5-v2 目前只是单任务、固定 tape 的 adapter smoke test**：run_phase4_v2_offline.py:102-160 只加载一个 microtask，edited=True 被硬编码，实际只演示一个默认策略路径。不得称为 failure-conditioned 算法效果验证。需增加多种离线故障场景并证明各分支确实被触发；结果仍须标记为 synthetic/fake-provider evidence。
5. **Clean-clone 脚本克隆本地 REPO 路径**：scripts/clean_clone_check.py 没有确认被克隆的 HEAD 等于 GitHub origin/main。应核对远端 SHA 或克隆准确的远端 URL/SHA，避免本地额外 commit 混入可复现性声明。
6. **状态文件仍保留 R1.1 的旧 blockers/next_goal**：status.json 顶层 blocker 仍声称 clean-clone、Proxy integration、Authorization 尚未完成，和 R1.2 报告冲突。必须区分历史 blocker 与当前未关闭项，更新当前审查状态。

## 结论

- 数据投影和离线重算：源码证据支持已有进展，但 Planner 未在 Executor 主机重跑测试。
- Proxy 接入：入口已接通，但当前存在 key 隔离、状态恢复、scope、入口认证和请求上限问题，不能启用付费 live。
- 算法适配器：离线 smoke 存在；尚不能证明真实 Agent 的 CEA-v0/v1 算法性能。
- TUN 级 DIRECT 仍为 DIRECT_ROUTE_UNVERIFIED，不得宣称网络路由已经验证。

**最终状态：CHANGES_REQUESTED。下一步 CE-DSH-P4-R1.3，仅离线修复，新增 DeepSeek 调用 0、预算 ¥0。**
