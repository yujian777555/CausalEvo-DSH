# CausalEvo-DSH — Phase 1 / Round 2（CE-DSH-P1-R2）

- 发布：2026-10-10
- Planner：GPT；Executor：Kimi
- 目标：将 Phase 1-R1 离线 Benchmark 与真正的 DeepSeek-Harness Agent 任务执行链安全连接，达到“可申请付费小样本 pilot”工程准备状态。
- 基线实现提交：c6276450fd97f0d1d047e151423bd5e2ecb21225
- 上轮验收：planner/reviews/CE-DSH-P1-R1-final.md（ACCEPTED / FROZEN / OFFLINE ONLY）
- 执行分支 main，最终 Commit+Push 与 status.json 按 planner/WORKFLOW.md 更新。
- **费用和授权红线：本轮 live API 预算 ¥0，所有真实模型网络请求被禁止。不把 Phase 0 的 ¥10 重复授权。全程用 fake transport / recorded non-sensitive SDK fixture / 干跑构建和对抗性测试。**

## 0. 科研目标不变

黑盒 API Agent 自进化研究：先构建可信的真实任务成功率基线，再探索失败机制诊断、受控干预、配对反事实重放与进化选择。本阶段不实现 CausalEvo 的因果算法，不宣布提升，不训练模型权重。第一版真实任务优先支持“编辑 workspace 文件 → 独立 judge 测试”的简洁场景；外部 SWE-bench Verified 仍是候选而非已经可运行的论文基准。

## 1. P1R2-S0 安全边界审计与文件读取隔离（阻断等级最高）

已发现：官方 `dsh-fs-sandbox` 的 workspace-write 限制 writes/edits，而 **reads pass through**。仅限制 tool shell + web，不能证明 agent 无法读取宿主机密钥、其他任务的 sealed/ref 文件；`DockerExecutor` 当前只用于 judge，不能保护 Harness Agent 的文件读取。

交付：
- `docs/PHASE1_R2_SECURITY_MODEL.md`：绘制 trust boundary：Harness runtime/tools、model provider、Agent workspace、secret holder/API key、Docker judge、task registry/hidden oracle、host。明确谁能读/写/联网。
- 提出并实现一个可以 **客观测量** 的严格 agent-visible FS allowlist，必须对 tool-fs read/read_image/write/edit 和 tool-fs-search glob/grep 都有效；首选容器化/隔离 execution world 或正确装配的受限 FS provider。如只靠现有 fs-sandbox（writes only）无法做到，就列 BLOCKED，不能用 prompt 禁止读取作为隔离措施。
- 增加 8 类对抗性测试：工作区外绝对路径读取；../ 目录穿越；symlink/junction 穿越；Git 工作树上游 sealed/ref；其他任务目录；宿主 API key/.env；glob/grep 搜索宿主与 registry；写入越界。Windows 与 Linux 路径都需考虑；容器环境需设计明确的可验证路径。
- **数据分离**：runtime 可访问的 agent workspace 只能有题目+可见测试+待修改代码；sealed/reference 文件须保存在容器/进程读取边界外，而非只在 Python 对象字段中“没有传给 Agent”。
- 记住：microtasks sealed/reference 已经在公开 GitHub，不能当成论文真正的未知 holdout；为未来独立私有 holdout 设计不入 Git 的存储与审查门槛。
- LocalTrustedExecutor：非可信 agent 产物不得因 Docker unavailable 而 fallback host execution；将“只跑可信内容”尽可能变为明确 runtime guard + 安全拒绝，注入测试。任何 executor 默认路径不能在 live 模式选择 local-trusted。

验收 S0-Gate：所有 FS 读取/搜索越界都实际被拒绝，且 agent 编辑自己的 workspace 正常。否则最终状态 BLOCKED，不得进入有凭据 live；但其他离线任务可做完。

## 2. P1R2-S1 DeepSeek-Harness 任务桥接（fake provider 必须可运行）

交付 `src/causalevo/eval/harness_agent.py`（路径可按架构调整）和无密钥 CLI：
- 使用已固定 SDK/runtime 版本调用 DSH，启动单任务单 Session，支持 B0、B1；不可为完成任务自行改用 LangGraph 或重写整个 Agent。
- 统一接口 `AgentRunOutcome`：任务 id、policy id、sealed-free workspace、session events、tool event summaries、finish_reason、content hash、cost accounting、失败类型；与现有 `Judge`/`TaskTrace` 衔接。
- **可用的离线执行模型**：使用 Fake LLM Adapter（在 Harness protocol 层）或 record-replay transport，确保相同的 Harness 状态/工具分发管线被真的经过；直接让 FakeAgent 修改文件不算该 gate；如果 SDK 不支持替换底层 provider，提供可检查的最小 patch 和协议 mock，准确注明 fake 层位置。
- 现有 DockerExecutor Judge 保持只读，Agent 编辑通过受限 FS provider 在隔离 workspace 完成；不可把宿主 DSH 进程和 Docker Judge 混称一个安全边界。
- 完成 agent→tools→workspace edit→independent judge→trace/metrics 的真实本地端到端（通过 fake provider，非付费 API）；包括 noop、正确修复、错误修复、错误 tool call、timeout、异常退出与工具超预算。
- Phase 0 的 100 条 raw live calls.csv 及 Phase 1-R1 的 26×2 offline reports 原样保留，新增 run_id 结果。

## 3. P1R2-S2 运行时公平预算与真实 Token 记账（离线注入）

必须实现可复验实时阻断，不止静态 `Budget` dataclass：
- B0 和 B1 共享相同的 max_provider_calls、**输入+缓存+输出的实际计费预算**及输出 tokens、tool calls、walltime 限额；B0 只进行固定策略，B1 reflection 和 reattempt 必须从同一额度扣除。
- Provider 发出前预算预留保守 upper bound；接收 settled usage 后扣真实计费 token 桶，所有 provider attempts 都被计入，包括工具调用生成的多步请求和失败重试。若 usage 缺失或身份不明，标 `unknown_cost`、stop；不把失败当免费。
- 多步/重试的独立请求身份检查：对无唯一 request-id、同 step 等量 usage 的 events，**不能靠 usage 值判同一请求**。无法证明去重时 fail-closed；离线对撞 fixture 必须验证两次相同 Token 值不会被低估或误记。
- 预算内 B1 reflection 分配清晰：一调用作初解、一调用作反思重试（或其他经固定的有效划分）；每个过程的 tool call、context length、cache miss/hit 和已用预算追踪到同一 task。
- 记录可审计 `provider_attempts`、`tool_attempts`、`known_input_tokens`、`cache_read_tokens`、`output_tokens`、`known_cost_cny`、`unknown_spend_attempts`、`budget_stop_reason`。预算超限时应安全中止并 Judge 判状态。
- 区分 provider 超时、工具执行超时、Docker judge 超时、最终 task success 的语义。

注意：输出 token cap=2048 是 Phase 1-R1 的静态 envelope。真实编程任务很可能不足，任何预算变更须先同口径修改 B0/B1 并记录原始/更新配置，不能为了让某个方法成绩更好而单独加预算。

## 4. P1R2-S3 判分隔离和不可泄漏事件设计

- Agent 不接触独立 Judge 的 sealed tests/ref 以及未来 hidden benchmark labels。
- 当前 `pipeline.FakeAgent.act` 把 `api_response_observed=True` 视为 fake 事件，需要改成真实可审计的 schema：`provider_kind=fake|replay|live` 与 `model_invoked=false|true`，`api_response_observed` 仅在真实 live API 时使用；旧 Phase 1-R1 报告不覆盖。
- `TaskTrace` 既能保留必要的错误机制特征和工具调用顺序（用于未来 CausalEvo 诊断），又必须去除密钥/敏感原始输出/不可公开的 sealed oracle；建议 redacted event graph + per-step hashes、token/cost ledger 和外部离线 replay references。
- 不把 `policy_id`、hidden test 输出、reference patch、judge verdict 回传给 Agent。sealed/test split 不能成为模型工具可读文件。
- 运行记录固定仓库 SHA、DSH SDK/runtime 版本、patch SHA、容器镜像 digest、任务包 hash、有效配置 hash、provider/model、timestamp、seed。

## 5. P1R2-S4 Benchmark 规模和可行性验证（不收费）

- 保留 26 个 microtasks 作为工程 smoke，不将它们的 sealed_test split 当做论文 final unseen test；公开 sealed/reference 文件已可见。
- 候选主基准 `SWE-bench Verified`：核对官方最新 CLI、license、可用数据/镜像、500 task 集；选择 2–5 个适合 pilot 的实例并记录 instance id、仓库版本、预计 CPU/disk/time。可下载元数据做审计，但不要在没有用户确认/环境条件时批量下载巨型镜像；第三方许可/资源若不可确认则标 NOT_VERIFIED。
- 外部真正独立 eval 不应在上游公开答案或 sealed 元数据上做方法调参；建议将难易梯度、修复大小/上下文长度及 leak 风险记录，确保后续不会因模型能力过低导致 0/全部的 floor effect。
- 设计等成本 B0/B1 pilot 的实验矩阵：先 smoke 3–5 小任务再扩展 20–30 任务，优先 2–3 个 paired seeds；明列统计置信区间和不受控的 provider stochasticity。此处**仅生成测量方案与保守预算评估**，不能发送真实模型请求。

## 6. P1R2-S5 验收测试与交付文件

- tests：新增至少 18 项有意义的测试，重点 agent FS read isolation、symlink/search、budget failure、重试计量事件碰撞、B0/B1 真实运行时平价、offline protocol mock end-to-end、judge 隔离、manifest hash；全部 Phase0+P1-R1 回归持续通过。
- CLI 必须支持 `--dry-run` 或离线 fake/replay；付费模式默认禁止：即使环境有 `DEEPSEEK_API_KEY`，没有 **单独发放的 Phase 1 live 授权**也必须拒绝。不可复用 Phase0 的 ¥10；不可在测试中访问 DeepSeek 域名。
- 文档：`docs/PHASE1_R2_SECURITY_MODEL.md`、`docs/PHASE1_R2_HARNESS_BRIDGE.md`、`docs/PHASE1_R2_RESULTS.md`、`docs/PHASE1_R2_PILOT_DESIGN.md`、`planner/executor_report.md`，配套 configs/ tests/ results/phase1/r2-offline/ manifest。
- 状态：交付工程全绿、S0 Gate 通过时设置 `READY_FOR_REVIEW`，next_actor=GPT-Planner；安全 gate 未过则 `BLOCKED` 并记录最小复现，禁止标为 ready-to-live。
- GitHub：提交 + 推送 origin/main，HEAD == origin/main、工作区 clean、列所有证据 SHA、运行真实命令和通过/失败/跳过数量。

## 7. 严格停止条件

即使所有离线测试通过，本轮也只能得出“Phase 1 R2 已具备可审计安全边界及离线 fake protocol integration”。**不得进入真实 DeepSeek-Flash B0/B1 pilot、Phase 2、或任何自进化实验**。是否授权小额 live pilot 由用户另行明确许可，Planner 发布后续单独计划和预算。发现 FS 泄漏、身份不明重试或真实 token 预算无效时，停机/报告 BLOCKED。
