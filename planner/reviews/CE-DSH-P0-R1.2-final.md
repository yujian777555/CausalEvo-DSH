# CE-DSH-P0-R1.2 — Phase 0 最终 Planner 验收与冻结

- 日期：2026-10-10
- Executor 提交：a7baa8979fb72860ad070f5e66ddf6d949cc0962
- 最终结论：**ACCEPTED / FROZEN / DELIVERABLE**
- 下阶段：CE-DSH-P1-R1；唯一执行计划由 planner/latest_plan.md 发布
- 审阅方式：读取 GitHub origin/main 已提交的源码、测试、报告、数据及 Git tree；没有在 Planner 环境重新运行 Kimi 的 pytest 或访问 DeepSeek 账户后台。

## 1. 最终核验

| Gate | 结果 | 审查依据 |
|---|---|---|
| Git/交付 | PASS | GitHub main HEAD=a7baa897...；R1.2 提交主体 d1bb542...；预期交付存在 |
| F2.1 全 attempts 计费桶 | PASS（源码+fixture） | benchmark.py 增加 *_all_attempts 主账，保留旧 final-attempt 栏位，汇总与费用一致性测试 |
| F2.2 assistant/attempt 提取 | PASS（离线构造事件） | usage.py 处理 message/attempt、data.usage/final stream usage、多重事件及冲突时 fail-closed；tests/test_usage_attempt_events.py |
| F2.3 对账 | PASS | 6/6 对账断言有提交证据；不可变 live CSV Git blob 一致，历史总量不变 |
| 自动测试 | Executor reported 79 PASS | tests/ 源码存在；没有 Planner 本地独立重跑 |
| Fake dry-run | Executor reported 100/100 calls | 只视为调度/文件写入离线测试；不视为模型任务成功或真实性能 |
| 费用 | HISTORICAL ESTIMATE ONLY | 100 次成功计量，off-peak 估算约 ¥0.0460417392；真实账单不可验证 |
| 下一阶段边界 | PASS | Executor 按要求停在 Phase 0；无新增 live 结果提交 |

## 2. 历史冻结数据（p0live02，不准修改原始 CSV）

- source: results/phase0/live/calls.csv
- Git blob SHA: 95d2fc112d37b4ad409190d3aba242276519613c
- 报告的文件 SHA-256: 1961bdd81a7f6a4ad4169d6f246530ed3df3170f70948f85de13ca136e364c59
- 100 条 model usage 记录（A/B/C/D 各 25，单次 attempt）
- uncached_input=27316、cache_read=29184、total_prompt=56500、output=3833
- weighted cache hit = 29184 / 56500 = 0.5165309734513275；mean per request=0.45983795734851773
- finish_reason completed=59，max-tokens=41；历史 JSON 任务有效性不可验证：task_valid=unknown
- off-peak token-rate 估算成本 CNY=0.0460417392，peak 假设上界=0.0920834784；actual billed unknown/null
- 128-token 粒度只是观测推断。A 组长度随 Session 增长混杂；D 组不验证 in-history system update。

## 3. 非阻断残留风险与后续限制

RISK-1（下阶段 live retry 启用前必须解决）：
`src/causalevo/usage.py` 在同一步中缺少 attempt 唯一 ID 且有等量 usage 的多个真实失败尝试，不能可靠判断是一条事件的重复，还是不同但恰好耗时等量的服务端请求。当前去重规则在这一特殊情形可能低估 Token 费用。**Phase 0 的原始 100 条全为单一成功尝试，故不受此风险影响。** 不得在 Phase 1 直接宣称 arbitrary multi-retry accounting 已完全证明；应通过日志事件身份或保守拒绝处理，补 fixture；复杂 Agent 的 live retry 保持关闭直到独立 Gate 通过。

RISK-2：计费金额为费率估算，平台余额显示精度不足以验证最终真实扣费，不允许将 visible delta=0 写成实际不收费。

RISK-3：no-tools Patch 在 Phase 0 合适，但 Phase 1 的工具型任务必须构建独立、最小权限、可重置环境；不能将主机持久 Shell 简单打开后作为沙箱。

RISK-4：开发阶段不应将固定微基准的成功率当作论文效果；必须引入独立的公开基准和隐藏评价集。不能将缓存效率和算法自进化收益混为一谈。

以上属于未来扩展边界/外部计费证据限制，**不推翻当前 Phase 0 的工程验收**。

## 4. 冻结约束与签发

Phase 0 已完成足以支撑 Phase 1 离线 Benchmark 工程的最小可审计基础设施。历史结果/原始 CSV 必须保持只读；任何未来修订新增实验 run_id、结果目录和独立记录，不得覆盖 p0live02。Planner 正式允许转入 Phase 1 规划，但 Phase 1 真实 API 调用需新的明确预算授权，Phase 0 的 ¥10 上限不可被自动沿用。
