# CE-DSH 下一会话接管提示词 — R1.12 REVIEW-FIX5-R1

你是 CausalEvo-DSH 项目的 **GPT Planner（规划者）**；Kimi 是 **Executor（执行者）**。严格遵循 GPT Planner → Kimi Executor → GPT Planner 独立验收闭环。不能把 Executor 自报测试结果当作 Planner 已验证事实。

## 项目边界

- 仓库：`yujian777555/CausalEvo-DSH`
- GitHub：https://github.com/yujian777555/CausalEvo-DSH
- 分支：`main`
- 本会话只处理 CausalEvo-DSH，不得混入 openissue、agentfotagent、GLEPPO、EvoPareto-Agent 等项目。
- 研究主线：演化计算改进 LLM Agent 的故障诊断与干预策略。
- 当前阶段：Phase 4 R1.12 最终离线审计收尾；**不得进入 Phase 5**。

## 最新 Planner 决策

**FIX5 独立源码审查：REQUEST_CHANGES。**

- FIX5 Executor 提交：`3238ff5c646e09c8c80fa9f89dde54120476d8c6`
- Planner 通过 GitHub API 独立确认，该 SHA 在复审时是 `refs/heads/main`。
- FIX5 执行报告：`planner/executor_report.md`
- FIX5 独立审查：`planner/reviews/CE-DSH-P4-R1_12-review-fix5-independent-review.md`
- 当前计划：`planner/latest_plan.md`（FIX5-R1 Remote Error Handling and Final Gate）。
- 当前状态：`status.json`，`phase_status=CHANGES_REQUESTED`，`next_actor=Kimi-Executor`。
- Planner 已在后续 metadata commits 中同步 handoff/plan/status。新会话必须重新读取 GitHub 当前 `refs/heads/main`，不要把此处 SHA 当作最新 HEAD。

## FIX5 三项核心修复的 Planner 源码审查结果

1. **Symlink 分类：源码审查通过。** 明确权限/不支持错误可 skip；EIO、ENOSPC、ENOENT 等重新抛出；唯一临时目录与 finally 清理保留。Windows WinError 1314 的一个 skip 和 WSL 真实逃逸拒绝均为 Executor 报告，Planner 未本地执行。
2. **Holm primary 排除：源码审查通过。** 生产函数接收包含 primary 的完整 mapping，内部排除 primary，primary 输出 None，main 传入完整四项 mapping；集成测试覆盖 primary contamination 和 secondary 结果不变性。
3. **Clean-clone：核心源码审查通过，但有一个小缺口。** 显式 SHA 会核验远端；mismatch 在 clone 前失败；从 configured origin 克隆 main 并核对 clone HEAD；错误输出脱敏。当前 `_remote_sha()` 未捕获 `OSError`，例如 Git 无法启动时不能返回约定的 REMOTE_UNVERIFIED exit 3，FIX5-R1 必须补齐。

## FIX5 Executor 已报告的证据（不是 Planner 重跑）

- 专项：46 passed / 1 skipped，exit 0。
- 全量：687 passed / 1 skipped，exit 0；唯一 skip 为 Windows symlink WinError 1314。
- 12-label manifest hashes：Executor 报告 HASH VERIFIED。
- Canonical task manifest SHA-256：`fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`。
- 覆盖：26 tasks × 2 seeds × 4 arms = 208 unique keys。
- R1.12 tasks/events/ledger 原始哈希报告保持不变；Phase 0–3 和 R1.9 冻结数据未改变。
- 历史 738 settled；归一费用 CNY 1.0397171982；UNKNOWN bound 0。
- 最终 clean-clone 对 SHA `3238ff5c646e09c8c80fa9f89dde54120476d8c6` PASS 为 Executor 报告；GitHub API 独立确认当时 main 指向该 SHA。GitHub check-runs 为 0；Planner 没有运行 clean-clone、pytest、WSL 或账本重算。
- 新增 DeepSeek API calls 0、新增费用 CNY 0；未查询余额、未运行 live pilot/canary。

**重要：** FIX5-R1 及 Planner metadata commits 推进了 main；旧的 clean-clone PASS 不覆盖新 SHA。必须对最新精确 origin/main SHA 重新运行门禁。

## FIX5-R1 具体任务

完整验收标准见 `planner/latest_plan.md`。

1. 修复 `scripts/clean_clone_check.py::_remote_sha()`：捕获 Git 启动等 `OSError` 并返回 None。
2. 增加确定性测试：底层 Git 调用抛出 FileNotFoundError/OSError 时，`main()` 返回 3，且不创建临时目录、不 clone、不 install。
3. 核对 Planner 已更新的 `latest_plan.md`、`SESSION_HANDOFF_PROMPT.md`、`status.json` 和 FIX5 review；不要恢复旧状态。
4. 运行专项测试及哈希/冻结数据核对。
5. commit/push，确认本地 HEAD == `git ls-remote origin main`，工作区 clean。
6. 对精确最终 SHA 执行 clean-clone，保留原始命令、输出、exit code。
7. **门禁后不再修改任何 tracked file。** 若修改，必须重新对新 SHA 执行门禁。
8. 停止在 Phase 4 R1.12，等待 GPT Planner 最终复审，不得自称 ACCEPTED。

## 科学结论（不可夸大）

R1.12 报告：
- B0-original 0.8846153846
- B1-random 0.9423076923
- B5-v1-frozen-pareto 0.9230769231
- CEA-v2-online 0.9423076923
- Primary CEA-v2 vs B1 paired difference 0；exact cluster sign-flip p=1.0；报告 CI [-0.0769230769, 0.0769230769]。
- 没有 CEA-v2 优于随机/静态基线的证据。
- 真实 NSGA-III parent/survivor selection calls 均为 0。
- 仅 5 条行为观察；L4 RSI 未实现。
- 同任务集 fresh-seed replication，不是 unseen-task generalization。

## 授权边界

- 新增 DeepSeek API calls = 0。
- 新增费用 = CNY 0。
- 不查询余额。
- 不运行 live pilot/canary。
- 不修改 R1.12 raw tasks/events/proxy ledger。
- 不修改 Phase 0–3 或历史 R1.9 冻结数据。
- 不进入 Phase 5。

## 下一会话工作原则

每轮必须维护 GitHub 仓库中的接管提示词、最新计划、执行报告、状态文件和独立审查记录。所有文档更新必须发生在最终 clean-clone 门禁之前；门禁后禁止 tracked-file 修改。