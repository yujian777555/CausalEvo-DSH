# CE-DSH-P0-R1.2 — Phase 0 最终计量闭环修复

日期：2026-10-10
Planner：GPT；Executor：Kimi
审计输入 HEAD：28738e905efbec2525afa51edf4e5eb6256d0e5e
当前状态：CHANGES_REQUESTED（Phase 0 未冻结）
审查报告：planner/reviews/CE-DSH-P0-R1.1-review.md

## 0. 范围与硬约束

此次仅关闭 R1.1 剩下的两项计量缺口，不实施 Phase 1，不更改 100 条原始 live CSV，不新增任何真实 DeepSeek API 调用或费用。本轮无需重做缓存基准。保留已有 64 项测试、离线 dry-run 和原本的 phase0/live/reconciliation 证据；不得伪造实测数据。

## 1. F2.1 多次尝试的 Token 桶必须全部累计（P0）

问题定位：src/causalevo/benchmark.py::_row() 费用和 output_tokens_all_attempts 汇总了所有 Attempts，但 uncached_input_tokens/cache_read_tokens/cache_write_tokens/total_prompt_tokens/cache_hit_rate 只取最后一次 attempt 的 usage，导致带 usage 的失败然后重试成功时，费用和 Token 表互相不一致。

修复：
1. 每个逻辑调用保留列表 attempts[]；对所有有 settled usage 的 provider attempts 求和组成 billed_usage，逐请求显示最终尝试的 usage 可以保留专门字段 final_attempt_usage（不能冒充总账）。
2. CSV 主列 uncached_input_tokens/cache_read_tokens/cache_write_tokens/output_tokens_all_attempts/total_prompt_tokens/cache_hit_rate 必须以全部已计量 attempts 为准。若为兼容旧 CSV 更合理采用 *_all_attempts 新列，需要清晰定义且所有总体汇总、账单、断言统一使用所有 attempts；保证既有 100 条存量 CSV 可无损读取。
3. cache-write 某些 attempt 未上报时，cache_write_reported 需体现 **所有 attempts 是否完整上报**；不可仅用最后一个 attempt 的上报标识。未上报的值按已有策略标记缺失，不伪造成已上报 0。
4. 若存在未知费用的 attempt，summary 不能把已知 Token / 已知费用描述为完整成本；分别记录 known_measured_cost 与 unknown_spend_attempts，以及费用完整性标志。
5. 增加自动一致性断言：单条调用所有已计量 attempts 的桶和应等于最终 CSV 桶和，已知费率加总与 cost 列相符；overall 与 groups、CSV 必须相容。
6. test_retry_success_meters_both_attempts 必须断言 **输入各桶也累加了失败+成功两个 attempts**，再增加仅失败两次均有 usage 的测试。至少测试 peak、off_peak 计费与多次重试。不能只断言 cost>0 或 output_tokens_all_attempts。

## 2. F2.2 解析 assistant/attempt 事件中的 settled usage（P0）

问题定位：src/causalevo/usage.py::_usage_from_message_event 仅接受 assistant/message，但 Harness 失败/重试的 assistant/attempt 可通过 data.stream 中最终的 usage 帧记录计费。此时把它作为无用量失败会导致漏计或不必要中止。

修复：
1. 支持 assistant/attempt 的 data.stream 内最终 settled usage 帧；有明确 data.usage 时按上游契约解析，且优先 authoritative settled 位置。
2. 避免重复记账：同一 provider request 的 stream 多个累计 usage frame 只取最终值；只有不同 request/attempt 可以求和。评估 assistant/attempt 和 assistant/message 同时出现、可能指向同一 attempt 的情况，根据可证明的 turn/step/attempt identity 做去重，否则 fail-closed / 标明不能确定，禁止盲目加总。
3. 成功/失败分别提供带 usage 的真实事件结构近似 fixture 测试；覆盖 assistant/attempt only、stream 中多帧累计、assistant/message 事件、重复可疑事件及无 usage 异常。
4. 保留原有对未知费用请求 fail-closed 停机，但当 assistant/attempt 有可靠 usage 时必须记录费用；不能因为它是失败事件就丢弃。
5. 将上游事件结构依据固定到 docs/HARNESS_INTEGRATION.md，明确来自代码契约还是实际服务端观测，不能将构造 fixture 写成真实 API 实测。

## 3. F2.3 独立离线证据及报告更新

- 旧 results/phase0/live/calls.csv 的内容 SHA-256 固定为 1961bdd81a7f6a4ad4169d6f246530ed3df3170f70948f85de13ca136e364c59；不能覆写。
- 原始 p0live02 100 次调用全是 1 attempt，故 Phase 0 历史数字应继续是：27316 uncached / 29184 read / 56500 total prompt / 3833 output；cache hit=0.5165309734513275；估算 offpeak ¥0.0460417392。不能为了适配新结构更改数字。
- 新失败注入测试、reconciliation 与既有不变 CSV consistency tests 均通过，补充至少一个离线 CSV 端到端样例：metered fail → metered retry success → 对账一致；再提供 local_rejected 和 unknown_cost 样例。
- 更新 docs/PHASE0_R1_2_FIX_REPORT.md、docs/PHASE0_AUDIT.md、planner/executor_report.md、status.json；明确代码修复不意味着新的 API 实测。
- 真实扣费继续 actual_billed_cost_cny=null，历史 JSON task_valid=unknown；41 个 max-tokens 继续披露。

## 4. 验收 Gate

G1：失败 attempt + 成功 attempt Token 桶和与费用总账一致，测试可独立证明；
G2：assistant/attempt 的最终 usage 被正确识别，无累计分片/重复事件双重计账；
G3：unknown_cost（未能可靠得知是否计费）仍触发 fail-closed，known failed usage 仍计费；
G4：原始 CSV hash 不变，历史数据与报告一致；不修改旧 live 证据；
G5：本轮全部测试、100 次 fake dry-run 真实执行，给出 PASS/FAIL/SKIP 和命令；
G6：零新增 live API 调用，零新增收费授权；
G7：git push origin main，远端 HEAD == 本地 HEAD、工作树 clean，提供完整 SHA。

## 5. 提交与停止

完成后 Commit+Push，status.phase_status=READY_FOR_REVIEW，next_actor=GPT-Planner；报告本轮改动路径、验证命令、测试结果、事故与残留风险。在 Planner 独立验收前，绝不进入 Phase 1；不要修改科研目标或提前发表性能结论。
