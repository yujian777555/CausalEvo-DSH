# CE-DSH-P4-R1.1 — Phase 4 Evidence & Algorithm Fidelity Remediation

发布：2026-10-14
Planner：GPT；Executor：Kimi
审查源提交：bddb17d632ca40a36468d82bb4dad3fd41f37644
理由：见 planner/reviews/CE-DSH-P4-R1-review.md
状态：CHANGES_REQUESTED；**不得视为最终 CEA 优越性验收**。

## 绝对边界

**本轮纯离线，授权新增 DeepSeek / 任何付费 API 调用次数 = 0，额外预算 = ¥0。**
不得更改 results/phase0-3 历史冻结数据；不得改写、删除、选择性丢弃 Phase4 原始真实运行或负面数据；如追加注释使用独立带版本文件，清晰区分 2026-10-14 原始实验、事后代码修复与未来的新实验。
不得为争取显著性而重挑任务、改变 metric，或把 B5> B0 描述为已证明“因果演化有效”。
复用已完成的源码组件，拒绝大规模再造平台；不直接开始另一个付费/公开 benchmark。

## P4-R1.1-S1 逐任务证据恢复与 freeze（P0 阻断）

1. 确认本机 `results/phase4/live/phase4-live-20261014T110259Z/tasks.jsonl` 原始 312 行及可用的 scratch/smoke 证据。计算 SHA-256，对原始文件实施只读冻结，**先保留一份未改动原始副本**（可能包含敏感内容，不强制上传）。
2. 添加明确的 gitignore allowlist，仅发布符合公开安全标准的每 run 结构化表（如 `results/phase4/live/<run>/auditable_tasks.jsonl`，或者单独 CSV/Parquet）：任务 id、arm、seed、尝试标志、成功、失败类型、干预标识、调用次数、token/cache 桶、费用、延迟、run id、hash；不能包含 API key、私人目录、session 原文、hidden oracle、chain-of-thought。
3. 全量记录导入生成的 audit SHA / schema version / derived_from_sha256 / row order；不能改变任何 outcome，用独立脚本 reconcile rows → baseline_results/statistical_tests/cost_analysis/manifest，断言 n=312、arm×seed×task 独一无二、分组预算对应、p 与 CI 可再生。
4. 如果本地 tasks.jsonl 已不可恢复，报告 `EVIDENCE_UNAVAILABLE` / BLOCKED，并说明哪些统计不可复核；**禁止从已有汇总反向合成 312 行**。
5. 更新 .gitignore 保留原始 session logs 不追踪，但允许明确 de-identified/auditable rows；新增仓库 CI 在缺少逐任务证据时 fail，防止再次“本地 409 PASS、远端不能 PASS”。

## P4-R1.1-S2 算法保真性审计与真实策略接口（P0 阻断）

1. 生成 `docs/PHASE4_ALGORITHM_FIDELITY_AUDIT.md`：逐臂追踪真实调用路径（module:function、选择与更新是否执行、证据 hash）。当前 B4 是 heuristic、B5 是固定静态 bundle 的事实必须单独披露。
2. 不改写旧实验，重命名旧结果语义为 B4-proxy/static-rule、B5-Pareto-selected-static-bundle（原 arm id 保留，添加 `actual_policy_kind`），避免在论文里直称“CEA-v0/v1 端到端在线执行”。A1–A4 记录成历史离线构造或代理消融，不能当作独立 live ablations。
3. 添加一个新的、独立的 `CausalPolicyAdapter`（不侵入冻结阶段源码）：
   - B4-live candidate：必须调用已冻结 LinUCB controller `select_intervention`，载入指定 policy snapshot，明确 update schedule、no test leakage；
   - B5-live candidate：必须消费 NSGA-III 产出的冻结 Pareto genome id 与 phenotype，由 **预先约定的 failure context + fitness constraint** 选择策略，不允许硬编码与任务无关的双 prompt 文本充当 NSGA-III；
   - 说明离线搜索与 live 评估的边界，训练任务与评估任务隔离；任何根据测试集结果动态调参直接标记 leakage；
   - 用 fake provider / replay 完成相同输入 context→不同有效候选的行为与预算审计测试。
4. 这轮**只证明新 adapter 的离线行为**，不可把它的输出混入旧 312 行、更不许声称已补齐新的真实模型结果。

## P4-R1.1-S3 Provider 逐请求预算门（P0 安全）

1. 明确区分 `agent_attempts`（外层单任务执行次数）与 `provider_requests`（一个 Harness turn 内模型的实际请求数），并明文建立两套不同配额。当前 `RuntimeBudget.max_provider_calls=2` 与实测每任务 2–8 个模型请求冲突；需要稳定迁移方案和版本化规则，不可用术语调整掩盖。
2. 每个请求必须经过真实 Provider 网络发送 **前** 的授权 / 限额检查：request_id 去重、余额与 token 预算最坏上界预留；收到 usage 逐个 request settle，并计失败/重试费用；无 usage 或身份冲突 fail-closed。可通过受控 proxy 或 SDK provider hook 实现；旧后验预算仍保留对账用途。
3. 建立隔离 fake SSE provider：一次 Agent attempt 模拟 3–8 个子请求，证明 cap 触发于下一条请求发送前而非整轮收尾后；同等 usage 不同 request_id 不去重，丢 usage / 401/500/EOF/stream reset 停机；kill 时必须保存 partial ledger。
4. 全局预算在逻辑 task 内实时生效，而不是在一次完整 run 返回后调用 `gate.record_spend()` 才计算。
5. 之前同一 run 的多次 provider requests 可能已超出“每任务 ≤2 provider calls”的文字口径：在报告中不改变历史真实事实，标注 protocol discrepancy 和影响范围。

## P4-R1.1-S4 统计可靠性与报告质量（P1）

1. 在逐任务数据恢复后，原分析照旧保留为 `legacy_iid_paired`，另新增基于 `task_id` cluster bootstrap（采样 26 个 task clusters，cluster 内保留两 seed/六 arm）与 task 聚合 sensitivity；报告 CI 与 score difference、随机对照的方向，不做 p-hacking。
2. 保持事先冻结的 B5 vs B1 主对照，即使仍是负面；B5 vs B0 只作为有 retry budget 混杂的辅助比较。
3. 计算 first-attempt success 与 recovery 的 per-arm paired 表、retry frequency、工具/模型请求计数、费率估计；更高价格不是方法贡献，切勿将 B0 一次 vs B5 两次视作纯算法效应。
4. 澄清随机 seeds 只控制 B1 及离线随机源，并不等价于 DeepSeek 远端采样可控；如存在 run order/time drift，单列 limitation。
5. 对 `PHASE4_FINAL_EVALUATION.md` 发布 **增补**（例如 `docs/PHASE4_R1_1_AUDIT_ADDENDUM.md`），原始负面结果、样本量、费用数字不可偷换。写清截止日期与实验协议历史修改痕迹。

## P4-R1.1-S5 下一轮真实 benchmark 的预注册草案（只设计，不开销）

- 验证 SWE-bench Verified 3 个已冻结 pilot instance 的官定 oracle/容器一致性（若需要大量镜像下载或外部环境不可用，标 NOT_VERIFIED），明确 judge 可以以独立 benchmark 运行，且不得把公开 microtask 成绩当论文主结果。
- 控制 ceiling effect：仅在预定义难度层筛选，不得依据 CEA v1 在具体任务的成功结果挑样本。
- 下一轮强基线：fixed two-attempt retry、random same envelope、rule-based、LinUCB real policy、NSGA-III policy adapter、必要 ablations；方案写明预注册统计、预算、停止规则以及探索性小试与确认性试验分界。
- 用户未明确批准新预算前，不得运行 DeepSeek live pilot。

## 交付和验收门

新增/修改建议：
- planner/executor_report.md、status.json
- docs/PHASE4_R1_1_AUDIT_ADDENDUM.md
- docs/PHASE4_ALGORITHM_FIDELITY_AUDIT.md
- docs/PHASE4_R1_1_PROVIDER_BUDGET_GATE.md
- docs/PHASE4_NEXT_PILOT_PREREG.md
- scripts/reconcile_phase4_rows.py 与相关 tests
- results/phase4/live/.../auditable_tasks.jsonl（安全去敏，原始副本只读）
- results/phase4/audit/（统计、hash 清单、limitations、test report）

Gate A：旧 312 行真实证据可独立在 origin/main 解析重算，或者明确 BLOCKED，不可带病通过。
Gate B：algorithm fidelity 明确区分旧 proxy 与未来真正执行 CEA 控制算法，假 provider 证明新 adapter 与实际 algorithm 的输入/输出闭环。
Gate C：3–8 请求真实 Harness fake SSE 经过逐请求预算门，限额前置；所有异常 fail-closed，旧计费逻辑继续无回归。
Gate D：cluster bootstrap、初次尝试/重试混杂、统计显著性与实际数据一致，不重塑结论。
Gate E：任何结果文件均不泄露 secret/holdout，Phase0–3 frozen hashes 不变，所有旧测试与新测试真实运行；完整公开的 CI 证据可复核。
Gate F：新增真实 API 调用数=0；已有 2026-10-14 Phase4 结果仍如实保留，明确本轮预算 ¥0。
Gate G：Commit + Push main，核验远端 HEAD、本地 HEAD、工作树 clean。

结束后设置 `phase_status=READY_FOR_REVIEW`、`next_actor=GPT-Planner`；如原始数据缺失或门控未完成则设 BLOCKED/PARTIAL 并具体报告。停在 Phase 4，不自行进入进一步付费实验或 Phase 5。
