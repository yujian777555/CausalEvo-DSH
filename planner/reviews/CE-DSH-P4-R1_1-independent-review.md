# CE-DSH-P4-R1.1 — GPT Planner 独立代码与证据验收

- 审核 HEAD：`9c7148eb34020c50295a0bda52cef0647df9702b`
- 执行主体：`45a0bd290e33c40bf0ab2a7393bb566bfef40302`
- 结论：**CHANGES_REQUESTED / PARTIAL**（尚不能正式 ACCEPTED/FROZEN）。
- 范围：GitHub Connector 远端代码静态审计；Planner 未在 Executor 的 Windows/Docker 环境重跑完整 436 项测试，也没有调用付费 API。

## Gate A：实验逐行证据恢复 — 部分通过

远端 `results/phase4/live/phase4-live-20261014T110259Z/auditable_tasks.jsonl` 实际存在，314 行（2 行元数据 + 312 行 JSON），26 tasks、2 seeds、6 arms，每臂 52 条。Planner 直接解析提交文件，独立汇总 B0 42/52、B1 48/52、B2 46/52、B3 43/52、B4 44/52、B5 46/52；对应成本和 B5-B0 的 7/3、B5-B1 的 3/5 discordant pairs 与摘要一致。原始 `tasks.jsonl` 没有提交，因此不能独立验证去敏投影相对于本机原始文件的忠实度，只能验证投影自身以及投影和摘要一致。

**P0 未闭合：干净 clone 不能运行已有统计代码。** `scripts/analyze_phase4.py:load_rows()` 仍硬编码打开 `tasks.jsonl`；`scripts/recompute_phase4_stats.py` 调用该函数；`scripts/reconcile_phase4_rows.py` 先读取未提交的 original 并写出 projection；`tests/test_phase4_analysis.py`、`tests/test_phase4_integrity.py` 仍读取原始文件。本机 436 PASSED 不能证明 fresh clone 可运行。`auditable_tasks.jsonl` 前两行以 `#` 开头，不能直接当标准 JSONL 逐行 `json.loads`；请实现统一的 projection reader、schema/hash/row uniqueness 验证，令 CI 与重算脚本不依赖本机原始文件。

## Gate B：Algorithm Fidelity — 部分通过，live 未闭合

`src/causalevo/evolution/adapter.py` 新增实际 LinUCB 反序列化及 select 调用、读取冻结 Pareto 基因组并生成提示词的离线适配器，确认比之前的纯 static bundle 前进了一步；但 `scripts/run_phase4_pilot.py` / `src/causalevo/eval/live_pilot.py` 完全没有引用或实例化 `CausalPolicyAdapter`，live B4 仍旧是 heuristic、B5 仍旧是 hardcoded `CEAV1_BUNDLE`。

**P1 未闭合：** B5 `cea_v1()` 默认 `max(train_fitness[0],train_fitness[3])` 只选一份固定 genome，`intervention_for(failure_kind,edited,invalid)` 除 infra error 外并没有使用 edited/invalid/failure 类型做表型或前沿成员决策；将其称为 failure-conditioned deployment 不准确。`pareto_front_sha256` 当前只计算并记录，没有和可信 pinned expected SHA 比对。冻结前沿自身也存在重复基因型/表型；已如实审计 144→16 有效表型，建议后续做显式预选/可执行表型合法性校验。新 adapter 只具离线证据，不可宣称已有 live 性能。

## Gate C：Provider pre-send safety — FAIL（P0）

1. `src/causalevo/eval/budget_proxy.py` 实现了 isolated fake-SSE gate，但 `scripts/run_phase4_pilot.py:66-71` live 路径仍 `provider_endpoint=None, network="bridge"`，完全没实例化 proxy；真正实时模型请求**不通过**新门控。
2. `budget_proxy.py:_forward()` 构造上游 `urllib.request.Request` 时只转发 `Content-Type`，没有 `Authorization`/适用鉴权信息；FakeProvider 不校验真实凭据，单元测试无法发现此真实上线阻断。
3. proxy 绑定宿主 `127.0.0.1`，没有证明容器网络可达；SDK 是否发送 `X-Task-Id` 也未经集成证明，缺失时归为 `unknown-task`，破坏 per-task cap。
4. `BudgetProxy._check()` 只比较 `known_cost_cny + one_worst_case`，并发在途请求未从全局 cap 预留；两个**不同** body 并发均可在同一旧余额下被放行，严重违反全局 cap。`_inflight` 只拒绝相同 body，并不能解决费用并发。
5. ledger `_persist` 写入/flush 且在一次请求后结算，不等于网络前持久化 in-flight reservation；如果进程在请求发送后、结算前崩溃，欠缺可恢复的 unknown-spend/预留记录。
6. 原 SDK runtime 的 `RuntimeBudget(max_provider_calls=2)`/结算还是在 attempt 层；proxy 接入时需独立区分 request cap 与 agent attempt cap，连通后用 fake Harness→Container→Proxy→FakeProvider 做多轮端到端验证。

## Gate D：统计和负面结果 — 实质通过（结果口径有约束）

`statistical_tests_r1_1.json` 增加按 task cluster bootstrap，B5–B0 CI [-0.0385,+0.1923]、B5–B1 [-0.1346,+0.0577]，全跨零。先前 B5-vs-B1 随机无优势的负面结论保存。样本仅 26 microtasks，2 seeds，不是论文最终 holdout；论文不得宣传真实演化优化取得显著提升。

## Gate E：其他

- `tests/test_direct_connect.py:test_no_proxy_env_leaks_into_agent_container` 有 `... or True` 永真断言，应替换为实际行为测试；TUN 路由仍 DIRECT_ROUTE_UNVERIFIED，不能承诺真实出口已直连。
- GitHub compare 自前次 Planner `fd154747` 到提交 `9c7148e` 未显示 Phase 0–3 冻结数据文件的改动。
- Executor 声称 436 passed / 0 failed；Planner 尚未环境重跑。当前请求不批准新增 live API，预算 ¥0。

## 验收结论

**Phase 4 R1.1 = CHANGES_REQUESTED（部分有效）**。Gate A projection 存在/可人工重算，但 fresh-clone CI 未闭合；Gate B adapter-only 部分通过、live 尚未接入；Gate C pre-send safety 失败；Gate D 静态统计核对通过。下一步执行 `planner/latest_plan.md` 中 P4-R1.2 定向修复，仅离线。