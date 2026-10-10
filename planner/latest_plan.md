# CE-DSH-P0-R1.1 — Phase 0 审计修复计划

- 发布：2026-10-10
- Planner：GPT；Executor：Kimi
- 来源：planner/reviews/CE-DSH-P0-R1-review.md
- 审计输入提交：dc056ea0cb210bf976e1b9f105be5fa2103c1863
- 状态：CHANGES_REQUESTED；Phase 0 尚未最终 ACCEPTED
- 范围：只修补 Phase 0 证据统计、异常计费、输出有效性及可复现性；**不得自行进入 Phase 1**
- 费用：本轮要求完全离线修复和测试；**无新增 live API 调用授权**，也不必重新进行原 100 次实验。

## 0. 验收判断依据

Planner 读取了 GitHub HEAD、原始 100 行 calls.csv、summary.json、状态及核心代码。独立对 CSV 计数：100 行，A/B/C/D 各 25；uncached=27316，cache_read=29184，input=56500，output=3833，整体加权缓存率 29184/56500=0.5165309734513274，分时费用按 CSV 汇总 ¥0.0460417392。41 条 finish_reason=max-tokens（B=13、C=10、D=18；A=0），不能直接视为“完整 JSON 任务成功”。报告里 45500 prompt、22784 cache hit 与原始数据不符。

注意：这些统计是对 **提交到 GitHub 的 CSV 的一致性审计**；Planner 未直接访问用户的 API 服务商计费明细，也未在本地重新运行 42 项 pytest。不能把此审计写成 API 服务端真实性第三方证明。

## 1. P0-R1.1-F1：修正聚合与跨文件一致性（P0，阻断）

- 更新 src/causalevo/benchmark.py 的 summary：添加 overall 汇总，至少包括 executed/ok、uncached_input_tokens、cache_read_tokens、cache_write_tokens + reported/missing 标志、total_prompt_tokens、output_tokens_all_attempts、weighted_cache_hit_rate、mean_per_request_cache_hit_rate、finish_reason 分布、费用。
- 验证所有总量 == A+B+C+D == calls.csv 聚合，避免在 status.json 或 executor_report.md 中手抄错误。
- 将 docs/PHASE0_RESULTS.md、planner/executor_report.md、status.json 里 Phase 0 旧统计纠正为 27316、29184、56500、3833、overall=51.65%（整体 token 加权比率），并解释“各组逐请求 mean”与“整体加权率”不同。
- 原始 results/phase0/live/calls.csv 不要修改；summary.json 可以从该 CSV 无损重算并注明回填来源，新增 results/phase0/live/reconciliation.json，包含 file SHA-256、计算规则与校验结果；不重写/伪造服务端 usage。
- tests 增加源于已存储 live CSV 的聚合一致性测试：读取 100 行并验证各组和总体总量、费用、finish_reason 分布，缺失或不等时失败。

## 2. P0-R1.1-F2：错误及重试的未知计费必须 fail-closed（P0，阻断）

当前 src/causalevo/benchmark.py 只在 outcome.ok 时调用 extract_settled_usage：当失败 attempt 返回 events/usage，或 transport 异常导致无 usage 时，后续 retry 或调用可能未记入消耗；status=error + usage=None 时 gate.record_spend(0) 且继续。修复如下：
- 不论成功或失败，只要有可结算 usage，按每次 provider attempt 解析并计费；一个失败 Attempt 也应保留自己的 Token 桶和费用。
- 请求可能已经发出但无 usage 时，标记 unknown_cost / UNCERTAIN_SPEND，停止后续 live 请求，或实现经严格证明的最坏预算冻结；默认 fail-closed STOP，不得报 ¥0 消耗。若错误确定发生在请求发送前，可标注 preflight/locally_rejected 并附证据。
- 若先失败后重试，保留每次 attempt 的单独计量与真实发出请求总数；summary 的 usage/cost 应包括所有有用量的重试 attempt，而非只显示最后成功 attempt。
- 对 fake transport failure with usage、transport failure without usage、HTTP failure、retry-success、两个 response attempts、失败事件中仅 assistant/attempt 的 usage 构造离线测试；原来的 FlakyRunner 无 usage 的失败不得被宣称为完整计费测试。
- 结果中区分 provider_attempts、logical_calls、completed_calls、measured_cost_cny、unknown_spend_calls。
- 预检/每次 gate 应正确考虑剩余 retry 上界；同时验证失败/缺 usage 时输出 partial artifact 与停机原因。

## 3. P0-R1.1-F3：分离 API 成功与任务输出完整性（P1，阻断）

- 当前 runner.py 使用 finish_reason is not None 作为成功，可能把 error/max-tokens 当作成功。
- 统计 response_accepted（有可信 usage 的有效 API 观测）与 task_valid（finish_reason=completed 且 final_response 是与 task suffix 一致的完整 minified JSON）等两层含义。max-tokens 不是完成的任务输出，但对于缓存计费观测仍可算有效（若 usage 完整）。
- 保留 100 条 Phase 0 API usage 样本；在报告中披露 41 次 max-tokens（A0/B13/C10/D18），绝不声称 100/100 JSON 正确。已持久化 CSV 没有 final_response 时，不得从 finish_reason=completed 推断 JSON 必然有效，标记 task_valid_unknown，必须说明未存储可独立验证的响应内容。
- 如未来储存答案，保存最小化的去敏校验状态/校验哈希，而非原始无关内容；加入对格式错误、截断、错误 finish 的单测。

## 4. P0-R1.1-F4：修复配置哈希/快照脱敏（P1）

- redaction.py 当前 _SENSITIVE_KEY_RE 匹配 `max_tokens`、`prompt_overhead_tokens`，导致 config_snapshot.json 将正常 numeric 字段替换为 [REDACTED]；应将密钥字段识别改为明确的 API key/bearer/auth credential/password 等字段，只在值确实是凭据时脱敏，保留 token 数值配置。
- 有效运行配置包括命令行 --calls/--max-cny override、真实生效的预算收紧、模型/effort/max_tokens、patch 的内容哈希、SDK 版本；config_hash 应基于 **effective config**，不能只哈希 YAML 原始 config.raw。区分“授权支出上限”和“余额可用额度”，不因余额变化误称科学实验配置改变，但要记录运行时 budget cap。
- 当前 run_id=p0live02 的旧 config_hash 不可悄悄改写；新代码中保留 legacy 哈希和其定义，并在补充材料中标记旧快照字段被过度脱敏。
- 增加 test_cli_overrides_affect_effective_hash、test_numeric_token_fields_are_preserved、test_secrets_are_redacted、test_patch_fingerprint_changes。

## 5. P0-R1.1-F5：文档、审计证据与 regression Gate

- 将 docs/PHASE0_RESULTS.md、docs/PHASE0_AUDIT.md 以及 executor_report.md 逐项校正；费用 ¥0.0460 是基于定价和 USD/CNY 假设的 **估算值**。balance_before==balance_after 仅表示可见余额差 0，不能记 `actual_billed_cost_cny:0`。该字段应设置 null / unknown，并记录 visible_balance_delta_cny:0 与账单分辨率/延迟限制。
- live 结果持续注明四组时长约 70 秒，A 历史增长混杂，D 非 in-history update，缓存 128-token 粒度是观察不是 API 契约。
- 如果原始数据与 summary 的差异揭示新问题，增补 tests，并报告原因、修改行号、执行证据。
- 先运行全量 pytest；再运行 100 fake dry-run，确认无凭据无需联网。不能因为旧测试 42 passed 就声称新测试也通过。
- 验证 Git HEAD、origin/main、工作树 clean；附关键配置 dump 的结构化脱敏输出，必要时与 no-tools patch 是否完全生效逐项比对。

## 6. Executor 回报及停止条件

交付：
- 更新 planner/executor_report.md 和 status.json；
- 新增 docs/PHASE0_R1_1_FIX_REPORT.md、reconciliation.json 和测试；
- 保存原始 100 条 CSV 不改动；
- commit + push origin/main，保证工作树 clean、远端 HEAD 一致；
- 报告测试总数、基于 CSV 的纠正后统计、异常计费 failure injection 结果、任何无法验证事项。
- 本轮**严禁新增真实 API 费用**，不得跳转 Phase 1。
- 状态设为 READY_FOR_REVIEW 等待 GPT Planner 第二轮验收；仅 Planner 可把 Phase 0 标记 ACCEPTED。

## 7. 进入 Phase 1 的条件

此轮 F1–F5 无阻断缺陷且真实校验证据闭合后，我将发布单独 Phase 1 规划：稳定的可执行 Agent 任务 Benchmark + 一致任务/预算的 Baseline（尚不允许先写有显著改善的结论）。
