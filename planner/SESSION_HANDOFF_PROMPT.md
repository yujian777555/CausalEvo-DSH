# CE-DSH 下一会话接管提示词 — R1.12 REVIEW-FIX5

你是 CausalEvo-DSH 项目的 **GPT Planner（规划者）**；Kimi 是 **Executor（执行者）**。严格遵循 GPT Planner → Kimi Executor → GPT Planner 独立验收闭环。不能把 Executor 自报测试结果当作 Planner 已验证事实。

## 项目边界

- 仓库：yujian777555/CausalEvo-DSH
- GitHub：https://github.com/yujian777555/CausalEvo-DSH
- 分支：main
- 本会话只处理 CausalEvo-DSH，不得混入 openissue、agentfotagent、GLEPPO、EvoPareto-Agent 等项目。
- 研究主线：演化计算改进 LLM Agent 的故障诊断与干预策略。
- 当前阶段：Phase 4 R1.12 离线审计修复；**尚未最终验收，不得进入 Phase 5**。

## 最新 Planner 决策

**FIX4 独立审查结论：REQUEST_CHANGES。**

- FIX4 Executor 提交：717a1fbe8371a444c33f02ff9300c90505ec5ea7
- Planner 已通过 GitHub API 独立确认，该 SHA 在复审时是 refs/heads/main。
- FIX4 执行报告：planner/executor_report.md
- FIX4 独立审查：planner/reviews/CE-DSH-P4-R1_12-review-fix4-independent-review.md
- FIX5 执行计划：planner/latest_plan.md
- 项目状态：status.json，phase_status=CHANGES_REQUESTED，next_actor=Kimi-Executor。
- 本 handoff 和 Planner 状态/计划更新会产生新的 Planner 文档提交。因此新会话必须重新读取 GitHub 当前 refs/heads/main；不要把 717a1fbe 当作新会话的当前 HEAD。

## FIX4 已完成且通过源码审查的部分

- GitHub main 在 FIX4 复审时为 717a1fbe8371a444c33f02ff9300c90505ec5ea7。
- FIX4 从接管 SHA 5d1c12c3... 到提交 SHA 717a1fbe... 为一个 commit，修改 8 个文件。
- symlink 测试已使用唯一临时目录，并通过 finally 清理；独立 WSL 脚本创建链接、实际调用 verifier、断言 escape rejection 并清理。
- Holm raw-p 顺序与 lexical key 顺序的负对照现已非平凡。
- main() 当前确实先从比较列表中排除主比较，再调用 apply_secondary_holm。
- fake-provider smoke 目录只含 manifest.json 和 controller_state.json；manifest 标记机制接线测试，不是模型效果证据。
- FIX4 报告的全量测试为 665 passed / 1 skipped；Windows WinError 1314 symlink skip。Planner 没有本地重跑。
- FIX4 报告 exact-SHA clean-clone PASS at 717a1fbe...；GitHub API 独立确认 main 指向相同 SHA。Planner 没有本地运行 clean-clone。
- GitHub check-runs 查询为 0；本轮测试证据来自 Executor 本地终端报告，不是 Actions。

## FIX4 独立审查的三个剩余问题

### 1. Symlink skip 分类过宽（P2）

tests/test_r12_hashes.py 捕获所有 OSError 并 pytest.skip。这样 EIO、ENOSPC、ENOENT 等无关文件系统错误也可能被误记为 skip。

FIX5 要求：
- NotImplementedError 可 skip。
- OSError 仅对明确的权限/不支持错误 skip，例如 Windows WinError 1314、POSIX EPERM/EACCES、ENOTSUP/EOPNOTSUPP/ENOSYS。
- 对 EIO、ENOSPC、ENOENT 等不相关错误必须重新抛出，使测试失败。
- 增加纯分类器回归测试：权限/不支持错误为 unavailable；EIO 等无关错误不是。
- 保留唯一临时目录和 finally 清理。

### 2. Holm primary exclusion 没有成为生产函数的不变量（P2）

当前生产函数：

    return {primary_key: None, **holm_adjusted_by_key(secondary_raw_p)}

如果 secondary_raw_p 恰好包含 primary_key，字典展开会覆盖 None，导致主比较被 Holm 校正。当前 main() 外部过滤正确，但测试人为构造了已排除 primary 的 secondary map，不能保护函数免受 primary 污染。

FIX5 优先方案：
- 将 apply_secondary_holm 改为接收所有比较的 raw-p mapping（包括 primary）。
- 函数内部确保 primary_key 返回 None，只对其他比较执行 Holm。
- main() 将完整 raw-p mapping 传入，不要在函数外预先过滤 primary。
- 集成测试必须让 primary_key 实际存在于输入 mapping，并断言输出 primary=None、三个次要比较正确校正。
- 保留 lexical negative control、ties、累计最大值、单调性和 [0,1] 测试。

### 3. clean_clone_check.py 显式 SHA 绕过远端检查（P2）

当前 scripts/clean_clone_check.py：
- 如果命令行传入 expected SHA，就不调用 _remote_sha()；
- 使用 git clone str(REPO)，即克隆本地仓库路径；
- 成功消息却写作 HEAD == origin/main。

FIX4 这一次另有 Executor 报告的 git ls-remote 检查，且 Planner 通过 GitHub API 确认 main=717a1fbe...，所以本次目标 SHA 有外部佐证。但通用 gate helper 本身可能在本地有未推送 commit 时 false-pass。

FIX5 要求：
- 无论是否传显式 SHA，都必须查询配置的 origin/main。
- remote 无法确定时 fail closed。
- 显式 SHA 与 remote SHA 不一致时，在 clone/install 前失败。
- 优先 clone 实际 origin URL 的 main；若保留本地 clone，则必须先证明本地 HEAD == remote main == expected，并准确描述 clone source。
- 不得在未检查远端时声称 clone 的 origin/main 已验证。
- 添加显式 SHA / remote SHA mismatch 的确定性回归测试。
- 不输出可能带有嵌入凭据的 remote URL。

## FIX5 完整任务

所有详细文件与验收标准见 planner/latest_plan.md（CE-DSH-P4-R1.12-REVIEW-FIX5）。

完成 A–C 后：
1. 跑 symlink classifier/containment、Holm、clean-clone helper、analysis determinism、frozen-task-set 专项测试。
2. 跑全量 pytest，记录原始输出、passed/failed/skipped 和 exit code。
3. 验证 12-label manifest hashes。
4. 验证 canonical task manifest hash 仍为 fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483，覆盖 26 tasks × 2 seeds × 4 arms = 208 keys。
5. 确认 R1.12 raw tasks/events/ledger、Phase 0–3 和历史 R1.9 冻结工件未改。
6. 核对历史 738 settled、归一费用 CNY 1.0397171982、UNKNOWN bound 0；不得新增 provider 请求。
7. 在最终 commit 前更新 executor_report.md 和 status.json。
8. commit/push，确认 local HEAD == git ls-remote origin main，worktree/staging clean。
9. 用 hardened clean-clone helper 对精确 final origin/main SHA 执行门禁。
10. **门禁后禁止任何 tracked-file edit/commit。** 若改动了文件，必须对新 SHA 重跑门禁。

## 科学结论（不可夸大）

R1.12 committed analysis:
- B0-original 0.8846153846
- B1-random 0.9423076923
- B5-v1-frozen-pareto 0.9230769231
- CEA-v2-online 0.9423076923
- Primary CEA-v2 vs B1 paired difference 0; exact cluster sign-flip p=1.0; reported CI [-0.0769230769, 0.0769230769].
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

## Planner 下一步

Kimi 完成 FIX5 后，重新读取当前远端 main，检查所有代码和测试变更，核对 exact-SHA clean-clone 输出与实际 GitHub main 一致。清楚区分 Planner 已核查、Executor 自报、尚未验证的证据，再决定 ACCEPTED 或 REQUEST_CHANGES。不要只看测试数量。
