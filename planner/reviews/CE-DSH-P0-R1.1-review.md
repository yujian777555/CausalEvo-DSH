# Planner Review — CE-DSH-P0-R1.1 第二轮审计

日期：2026-10-10
审查提交：28738e905efbec2525afa51edf4e5eb6256d0e5e
**结果：CHANGES_REQUESTED（Phase 0 尚未最终 ACCEPTED）**
下一轮计划：CE-DSH-P0-R1.2

## 已通过的项目

1. GitHub main HEAD 与报告一致，工程源码及新测试均已推送。
2. 旧原始 CSV 在新旧仓库树中的 blob SHA 都是 95d2fc112d37b4ad409190d3aba242276519613c，Git 级验证未被修改。
3. reconciled summary.json: uncached=27316、cache_read=29184、input=56500、output=3833、weighted hit=0.51653097345、off-peak 估算=¥0.0460417392，吻合先前 Planner 独立逐行统计。
4. 已区分 response_accepted 与 task_valid；41 个 max-tokens 和存量响应内容不可验均已披露。
5. 红action字段不再把 max_tokens 和 prompt_overhead_tokens 误删，effective_config_fingerprint 引入 patch 和 SDK 版本。
6. 实现和测试中确实新增了 unknown_cost 停机及已知失败计费的逻辑；测试套件 64 passed 为 Executor 所报，Planner 未在本地重跑。无新增 live 费用的说法来自报告及仓库未增加 live 记录，不能独立证明平台后台没有调用。

## 阻断漏洞 #1 — 重试输入 Token 桶仍只算最后一次

src/causalevo/benchmark.py::_row:
- cost_peak / cost_tiered 对 attempts 列表累计；
- output_tokens_all_attempts 对 attempts 累计；
- 但 uncached_input_tokens / cache_read_tokens / total_prompt_tokens / cache_hit_rate 取 `usage = final.usage`，不是 all attempts；
- aggregate_rows 继续基于这几个主列计算全局 tokens。
因此带用量失败再重试成功时，报告的输入 Tokens 被低估，费用与所报告的 Token 桶不一致。

R1.1 新增 tests/test_failure_metering.py::test_retry_success_meters_both_attempts 只核对尝试数、metered_attempts 和输出求和，没有检查 **输入桶总量**，所以 64 tests 即便通过也无法否定该漏洞。

## 阻断漏洞 #2 — assistant/attempt 中的 usage 仍未解析

src/causalevo/usage.py::_usage_from_message_event 直接拒绝非 assistant/message 事件；extract_settled_usage 没有其他 assistant/attempt 通路。
DeepSeek-Harness 的 assistant/attempt 可在 data.stream 中保留被重试/失败且未提交 surface message 的模型尝试，模型用量可能存在；目前这种情况会被视为缺失用量并停机/丢失可用计量。R1.1 计划要求 assistant/attempt 的测试，但新增 tests/test_failure_metering.py 并无该事件类型 fixture。

## 范围与证据约束

仅继续修 F2 计费闭环，不重跑 Phase 0 的真实 API 缓存测试。主要问题在新失败注入分支，不影响已提交 100 条单次成功计量样本。官方源代码已确认 assistant/attempt 为失败尝试事件；实际 API 故障事件如何产生仍需独立实测才能完全归纳，这不应妨碍离线契约测试。

正式验收条件：以上两项在代码、失败注入测试、文档中同时闭合后，可考虑 Phase 0 ACCEPTED，并单独发布 Phase 1 基线开发计划。
