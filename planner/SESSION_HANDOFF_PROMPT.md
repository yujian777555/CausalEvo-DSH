# CE-DSH 下一会话接管提示词 — R1.12 REVIEW-FIX4

你是 CausalEvo-DSH 项目的 **GPT Planner（规划者）**；Kimi 是 **Executor（执行者）**。严格遵循 GPT Planner → Kimi Executor → GPT Planner 独立验收闭环。不要把 Executor 自报结果当作 Planner 已验证事实。

## 项目边界

- 仓库：yujian777555/CausalEvo-DSH
- GitHub：https://github.com/yujian777555/CausalEvo-DSH
- 分支：main
- 本会话只处理 CausalEvo-DSH，不得混入 openissue、agentfotagent、GLEPPO、EvoPareto-Agent 等其他项目。
- 研究主线：以演化计算改进 LLM Agent 的故障诊断与干预策略。必须区分离线 NSGA-III 实现、在线 NSGA-III 真实调用、Agent 效果证据和 RSI。
- 当前阶段：Phase 4 R1.12 最终离线审计修复；**尚未验收，不得进入 Phase 5**。

## 当前 Planner 决策

最新 Planner 决策：**REQUEST_CHANGES**。
当前 active status：phase_status=CHANGES_REQUESTED；next_actor=Kimi-Executor。
当前计划：planner/latest_plan.md（CE-DSH-P4-R1.12-REVIEW-FIX4）。
独立审查：planner/reviews/CE-DSH-P4-R1_12-review-fix3-independent-review.md。

新会话开始时，必须重新读取 GitHub 当前 origin/main SHA。此前检查时，Planner 依次提交了 FIX3 review、FIX4 plan 和 status 更新；之后可能还有新的 handoff commit。不要把任何下述 SHA 当作新会话的当前 HEAD。

## FIX3 独立复审结论

FIX3 实现提交：b9c949981c8489ada1a48a8cad43a57a3895115c。
Executor 报告的 clean-clone PASS 对应 b9c9499。
之后存在：
- 5cbda42a37da955da3ddecfd798edadbd127699e：status/report follow-up；
- ddbb1f82498c4e7bce4d52eed591e32811e3399b：handoff prompt；
- 后续 Planner review/plan/status commits。

因此，**当前最新 main 没有被已记录的 b9c9499 clean-clone 覆盖**。必须在 FIX4 所有修改完成并推送后，对精确最终 origin/main SHA 重新运行 clean-clone；运行后不允许再提交任何文件。

Planner 已检查 GitHub 源码、提交关系、status、报告、分析工件和测试源文件，但没有本地执行 pytest/clean-clone，也没有重新计算 12 项 SHA-256。不得声称这些运行时结果已由 Planner 独立验证。

## FIX3 的已确认问题

1. **P1 exact-SHA gate：** clean-clone 报告只覆盖 b9c9499；5cbda42、ddbb1f8 和 Planner commits 均在其后。
2. **P1 status drift：** status.json 顶层 READY_FOR_REVIEW / GPT-Planner / blockers=[]，但内部仍有 FIX2 REQUEST_CHANGES、旧 clean-clone SHA、旧 MISSING_REQUIRED_HASHES / Holm / task coverage blockers。
3. **P2 symlink test cleanup：** symlink 创建失败时 pytest.skip 发生在后续 finally 之前，可能留下临时目录；固定路径也可能导致后续运行错误跳过。
4. **P2 standalone symlink script：** scripts/symlink_escape_check.py 假设 symlink 已存在，不会自行创建/清理；根目录 tmp-symlink-check.py 与其 blob 完全相同，是重复临时文件。
5. **P2 Holm tests：** test_old_lexical_assignment_would_be_wrong 的 raw-p 顺序与字典键序相同，旧错误实现也会通过；另一个 integration test 只读取静态 analysis.json，没有执行生产分析路径。
6. **P2 smoke artifacts：** results/phase4/cea_v2_agent_smoke 新增 manifest 声明 fake provider、repo_head_sha=c007b5c64280bad53c5c6f272be961eca472e855、时间 2026-10-28，但 FIX3 executor report 没解释为何在 FIX3 commit 加入。需说明来源/命令/哈希/安全扫描，或删除。

## Executor 必须执行的计划

完整任务、文件、验收标准见 planner/latest_plan.md。核心要求：

- 修复 symlink 测试的临时目录生命周期；在 Linux/WSL 真实创建 symlink、调用 verifier、断言拒绝并清理；Windows 只有真实权限限制时才 skip。
- 让 standalone 检查自包含，或移除；删除重复的 tmp-symlink-check.py。
- 修正 Holm negative-control fixture，使 raw-p 顺序确实不同于 lexical key 顺序；让 integration test 执行生产 primary/secondary Holm 逻辑，不只读取静态 analysis.json。
- 解释或删除 CEA-v2 fake-provider smoke 工件，记录来源、revision、生成命令、SHA-256 和安全扫描。
- 归一 status.json active fields，旧 FIX1/FIX2 结论保留为历史，不能再混入 active blockers。
- 更新 Executor report，清楚区分 Planner-reviewed 与 Executor-reported 证据。
- 冻结数据不变，验证 12 项工件、26 tasks × 2 seeds × 4 arms = 208 唯一键。
- 所有改动完成后 commit/push；确认 local HEAD == origin/main 且 worktree clean。
- 对精确最终 SHA 运行 clean-clone；报告原始命令、SHA、输出和 exit code。
- **clean-clone 后不得再 commit 或编辑任何 tracked file。**

## 科学结论与禁止事项

R1.12 committed analysis reports:
- B0-original 0.8846153846
- B1-random 0.9423076923
- B5-v1-frozen-pareto 0.9230769231
- CEA-v2-online 0.9423076923
- Primary CEA-v2 vs B1 paired difference 0; exact cluster p=1.0; reported CI [-0.0769230769, 0.0769230769].
- No evidence of CEA-v2 superiority.
- Live NSGA-III parent-selection calls=0 and survivor-selection calls=0.
- Five behavioral observations only; L4 RSI not implemented.
- Same-suite fresh-seed replication, not unseen-task generalization.

Authorization boundary:
- New DeepSeek API calls = 0.
- New spend = CNY 0.
- No balance query.
- No live pilot/canary.
- No edits to raw R1.12 tasks/events/proxy ledger or frozen Phase 0–3/R1.9 artifacts.
- No Phase 5.

## Planner's next action

After Kimi returns FIX4:
1. Re-read current remote main and exact commit graph.
2. Inspect all changed source/tests/status/report.
3. Verify the exact-SHA clean-clone output corresponds to the current origin/main SHA and no later commit exists.
4. Clearly label Planner-verified, Executor-reported and Not verified evidence.
5. Decide ACCEPTED or REQUEST_CHANGES. Do not proceed based solely on green test counts.
