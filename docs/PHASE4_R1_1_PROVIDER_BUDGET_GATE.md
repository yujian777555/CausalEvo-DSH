# Provider 逐请求预算门（P4-R1.1-S3 设计 + 证据）

日期：2026-10-14。实现：src/causalevo/eval/budget_proxy.py。

## 1. 术语分离（不再混用）

- `agent_attempt`：一次完整任务执行（RuntimeBudget.max_provider_calls 原语义实际是 attempt 内 LLM 请求计数；旧口径混淆已在 PHASE4_EXPERIMENT_PROTOCOL.md 修订章节记录）。
- `provider_request`：一次真实模型 API 请求。
- 两套配额：每任务 agent attempt 上限（协议冻结值）+ 每任务 provider request 上限（proxy 的 max_requests_per_task）+ 全局费用上限。

## 2. 机制

受控 HTTP 代理夹在 Harness runtime 与 provider 端点之间。每个请求在**转发前**完成：
request_id 分配 + in-flight 去重 → 授权检查 → 每任务配额 → 全局最坏费用预留 → 放行/429。
响应后按 SSE 末帧 usage 原子结算（预留 FIFO 释放；失败但可能计费的请求**不释放**、标 unknown 并全局停止）。逐事件追加落盘 ledger（kill 不丢账）。

旧的后验 RuntimeBudget 保留作对账；新 proxy 是发送前门控。live 路径接入方式：provider base_url 指向 proxy；proxy 上游直连 api.deepseek.com（ProxyHandler({}) 显式直连）。

## 3. 测试证据（tests/test_budget_proxy.py，10 项全过，3 连跑稳定）

| 场景 | 断言 |
|---|---|
| 3 请求正常 | 全部结算，成本累计 |
| 每任务 cap=3 | 第 4 请求 429 且**上游零调用**（发送前拒绝） |
| 全局预算不足 | 首个请求即 429，上游零调用 |
| in-flight 重复 body | 第二个 429 |
| 上游 500 | 标 unknown、全局停止、后续 429 |
| 缺 usage 的 200 | fail-closed 停止 |
| stream reset | fail-closed 停止 |
| 未授权 | 429，零转发 |
| 逐事件落盘 | ledger.jsonl 行数 ≥ 请求数 |
| 环境污染代理 | 上游仍直连（DIRECT 证明） |

## 4. 与旧数据的口径差异披露

2026-10-14 pilot 实测每任务 2–8 次 provider 请求：与旧文本"≤2 provider calls"字面冲突；历史事实不改，差异影响已在协议修订与审计增补记录。旧数据的计费完整性依赖事后结算；发送前门控自本轮起具备。
