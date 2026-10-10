# GPT Planner ↔ Kimi Executor 工作协议 v1

## 角色与唯一事实来源

- GPT Planner：读取仓库代码、测试与真实实验记录，做技术审计、论文方向决策、阶段任务规划、验收、后续任务发布。
- Kimi Executor：按当前计划实现、测试、保存可审计证据、提交并推送；不得替 Planner 宣布科研有效性。
- GitHub origin/main 是最终交接事实源，聊天表述及本地结果不能替代远端核验。
- planner/latest_plan.md 为唯一当前生效计划；status.json 为机器可读状态；planner/executor_report.md 为执行回报。
- 不在仓库中存储 API Key、个人敏感数据或不可公开的执行日志。

## 标准循环

1. Planner 读取 main HEAD、现有状态、关键代码与结果，发布下一阶段完整计划和 status.json。
2. Executor git fetch，校验计划 ID 与状态；无法满足依赖时记录 BLOCKED 而不是跳阶段。
3. Executor 实现任务、运行单元/集成测试，若有 live 权限才调用 API，实际成本可审计。
4. Executor 将结果和 evidence 路径写入报告及 status.json，提交推送并核对 origin/main。
5. Planner 重新读取仓库验证结论。只有 Planner 可发布 ACCEPTED 或要求返工的新计划。
6. 不允许在 Executor 报告中把尚未运行的测试写成 PASS。实验不成功也必须如实记录。

## 状态机

- PLANNED：Planner 已发布任务、Executor 尚未开始。
- IN_PROGRESS：正在开发或实验。
- PARTIAL：软件已有交付但尚缺要求的真实实验/验收证据。
- BLOCKED：有具体外部阻塞（例如缺 API Key 或外部端点不可用）。
- READY_FOR_REVIEW：执行者提交完所有要求的证据，等待 Planner。
- CHANGES_REQUESTED：Planner 判定需要修复。
- ACCEPTED：Planner 已验收，冻结本阶段结论。

建议使用 phase_status、plan_id、planner_review、last_executor_commit、tests、live_api、blockers、next_actor 等明确字段。改 status.json 必须保持合法 JSON，禁止将预期结果写成实际测量。

## 必要 Git 证据

- 本地 HEAD 完整 SHA 和 origin/main 完整 SHA；
- clean 或 dirty；
- 测试命令、测试通过/失败/跳过数量；
- API 调用实际成功/失败数、计费桶、价格源日期、累计实际/估算费用；
- 证据文件相对路径、受影响代码、下一轮建议；
- 若阻塞，写明何处失败、如何复现、避免泄露凭据。

## 研究质量红线

- 只与同模型、同任务分割、同评估预算的 Baseline 比较。
- 严格分离 Agent 自进化算法收益、系统缓存优化收益和硬件/调度差异。
- 不声称反事实重放等价于完整因果识别；实验需声明控制变量、随机性与局限。
- 外部服务/模型升级必须记录，不能假装固定版本。
- 禁止实验数据篡改、伪造 benchmark 结果、无授权扩大 API 支出或访问越权系统。
