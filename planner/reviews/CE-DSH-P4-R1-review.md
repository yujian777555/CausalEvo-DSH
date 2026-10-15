# CE-DSH-P4-R1 — Planner 代码与证据审计

审计日期：2026-10-14（系统日期）
审计 HEAD：bddb17d632ca40a36468d82bb4dad3fd41f37644
主体提交：e7656bd9d15609c2331187fe8e5ac35b25672664
**结论：CHANGES_REQUESTED — 工程 Pilot 有价值，但 P4 审计不可闭合、CEA-v1 优越性未证实。**
后续指令：planner/latest_plan.md，CE-DSH-P4-R1.1。

## 已经独立验证的事实

- GitHub origin/main HEAD = bddb17d...；提交包含 Phase 4 代码、测试、实验协议及摘要报告。
- 汇总 artifact 报告 26 microtasks × 2 seeds × 6 arms = 312 个任务运行，B0=0.807692，B1=0.923077，B2=0.884615，B3=0.826923，B4=0.846154，B5=0.884615。
- 已提交的 McNemar 表：B5 vs B0 discordant 7/3, p=0.34375；B5 vs B1 discordant 3/5, p=0.7265625。无优越性显著证据；随机干预均值最高。
- 已提交成本汇总每臂分别约 ¥0.12、总费率估算 ¥0.714923，与 manifest 中值相符；不等于已独立取得服务商完整真实账单。
- 论文最终 unseen benchmark 尚未运行：26 个 microtasks 的官方标记为 engineering_regression / paper_eval_eligible=false，内容公开；初始成功率 80.8% 提示 ceiling effect。
- Repo 报告 pytest=409 passed，证据仅来自 Executor 报告和已提交测试源码，Planner 未本地重跑。

## P0 阻断项 1：逐任务原始证据未上传

`results/phase4/live/phase4-live-20261014T110259Z/tasks.jsonl` 在完整 Git Tree 中不存在，GitHub fetch_file 返回 404；此前 smoke run `...110027Z/tasks.jsonl` 同样不在远端。.gitignore 统一屏蔽 `*.jsonl`，仅放行 Phase1 traces。虽然 `tests/test_phase4_analysis.py` 和 `tests/test_phase4_integrity.py` 在 Executor 本机读取本地 tasks.jsonl，但远端不能复算 312 条 paired rows 或判断指标、用量、配对与日志是否一致。

请勿把“本机存在”描述成“已经 GitHub 可核验”。优先发布仅保留结构化去敏字段的逐任务表及 SHA256 manifest；如本地原始日志丢失，必须标 BLOCKED 并保留现有摘要，不得逆向生成与摘要吻合的假记录。

## P0 阻断项 2：算法臂名称与实际执行逻辑不相符

`src/causalevo/eval/live_pilot.py`：
- B4: 不调用 Phase3.1 LinUCB `select_intervention`，按固定 if/else 判断执行干预。
- B5: 不调用 Phase3.2 NSGA-III 或 Pareto-conditioned selector，始终用 `CEAV1_BUNDLE = tool_validation + verification` 固定提示词。
- B2 同样属于固定规则，而并非经独立 failure diagnosis 的完整系统。
因此当前 B4/B5 对应“静态代理策略/已选定提示词”的真实性能，而不能直接写为真实 CEA-v0/v1 的算法闭环评估。现有 A1–A4 是替代臂/离线历史结果映射，不是独立 live 算法消融。必须修正文档映射并设计未来实际算法接入验证；禁止事后修改历史行或冒称算法执行。

## P0 阻断项 3：逐 Provider 请求门控不充分

`live_pilot.run_task_arm` 构造 RuntimeBudget(max_provider_calls=2...)；`ContainerHarnessRunner.run_task` 调用 `budget.before_provider_request(0.0)` 一次，然后事件流中仅捕获 tool/call；`_settle_budget` 在最终事件回收后结算多个真实 provider requests。已报告每任务 2–8 底层请求，按真正 provider cap=2 看存在超出。2026-10-15 的协议补记声称“2 调用”意指 Agent attempt，但源码 Budget.max_provider_calls 用于 provider attempts，需要分开两种限制。报告的事后清算不等于逐请求预授权、最坏成本预留或可靠实时 kill。
要求后续真正 live 前在 Provider transport 入口做每请求拦截或可证明等价的 proxy gate，按 request identity 预留并结算；禁止把放宽/重新命名静态 cap 作为修复。

## P1 统计和实验限制

- 同一个 26 任务在两个 seeds 复用，52 行的 IID paired bootstrap 与传统 McNemar 若忽略任务内相关性，可能低估不确定性；增加 task_id cluster bootstrap，并显示 26 个任务单位的 sensitivity analysis。
- B0 单次尝试，B1–B5 最多两次；B5 vs B0 因 retry budget 不等不能单独归因为进化。关键 B5 vs B1 同重试额度且仍未证明优势。
- seed 在 runner 中明确用于 B1 random RNG；未证明 provider 本身随机性被 seed 固定。避免声称“同随机种子控制 LLM 采样”。
- 在用户当前会话中没有独立核实实际预算批准的原始记录；Planner 不追溯反推授权，而是要求 Executor 提供可审核的审批记录或仅陈述运行时 gate。
- `docs/PHASE4_EXPERIMENT_PROTOCOL.md` 含事后口径澄清，应记录真实修改时间/commit 和预注册 version，不得将其视为“原先已定义”。
- 若独立 holdout 用于 Phase4 论文结果，仍须 separate license/dataset/oracle gate；现有 microtasks 只构成工程 pilot。

## 决定

**PHASE 4 = CHANGES_REQUESTED（审计与证据修复）**。
- 接受存量实验为探索性真实调用工程 pilot，不接受“真实 CEA-v1 优越性”“因果归因已证明”或“论文最终验证完成”。
- 现有摘要和负面结论只读保留；没有用户单独批准前不得再调用 DeepSeek API。
- 新计划 P4-R1.1 只做离线审计修复、预算安全门与下一轮实验设计，不重新执行付费实验。
