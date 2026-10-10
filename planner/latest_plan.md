# CausalEvo-DSH — Phase 0 执行规划（Planner 正式发布）

- Plan ID：CE-DSH-P0-R1
- 发布日期：2026-10-10
- 仓库：https://github.com/yujian777555/CausalEvo-DSH
- 目标分支：main
- 阶段状态：PLANNED / AWAITING_EXECUTOR
- Planner：GPT；Executor：Kimi
- 实际开发开始前先读取 planner/WORKFLOW.md、status.json、本文件。
- 本计划属于 Phase 0 基础设施与真实缓存测量；禁止提前将其写作“因果进化效果验证”。

## 0. 科研目标与边界

目标：以 DeepSeek-Harness + DeepSeek 官方 Flash API 构建可复现的黑盒 LLM Agent 实验平台，后续研究失败机制假设、受控干预、配对反事实重放以及进化接受门控。当前阶段只验证 Harness 集成、缓存、计量、隔离、版本化和基准测试可靠性。

原则：
1. 自进化是 Agent 系统级（Prompt / Skill / Tool / Workflow）的更新，固定云端模型权重；不可将其描述为模型权重自训练。
2. 缓存降低费用是工程目标；不能作为因果自进化机制学术贡献的替代。
3. 优先非侵入扩展、SDK 和插件；不得直接大规模改写上游 Harness。
4. 任何关于真实 API 命中率、价格、用量和模型表现的数字必须有调用原始证据；无凭据时明确 BLOCKED。
5. 不得让测试代码在用户真实工作区使用无限制 Shell；敏感凭据不得进入 Git、日志、报表或 Prompt。

## 1. Phase 0 任务

### P0.1 仓库基础结构与依赖锁定

- 初始化 src/causalevo/、benchmarks/、configs/、tests/、results/、docs/ 与必要的 pyproject.toml / lockfile；保留原 README 可补充项目入口。
- 编写 docs/HARNESS_INTEGRATION.md：说明 SDK 调用链、Session 生命周期、LLM request、系统提示词、工具注册和 usage 事件；注明对应 GitHub 源码路径与具体上游提交 SHA。
- 核验 Python SDK 与 DeepSeek-Harness 官方适配器的真实兼容版本；独立隔离工作空间和 DSH_HOME。
- 明确 provider=deepseek-official、实际 wire model id 与 SDK 默认模型 id 的区别；以已验证 API model id 为准，不默认把 deepseek-v4-flash 当作 deepseek-flash 同一固定版本。
- 初始化无密钥的 dry-run、离线 fake provider 和可选 live 模式。未提供 DEEPSEEK_API_KEY 则 live 禁止运行。
- 记录当前环境依赖和复现步骤，Windows PowerShell 优先，兼顾 Linux。

### P0.2 工具、会话与网络安全

- Phase 0 基准任务仅生成固定、短文本；模型无需访问命令、文件系统、网络或第三方工具。
- 明确检查并禁用 SDK minimal profile 默认持久 Shell / dangerous permission；仅设置 Prompt“不要调用工具”不算有效隔离。无法确认工具彻底禁用时，使用不暴露这些工具的定制 profile 或隔离容器，live 阶段不得绕过该门槛。
- 禁止任意 Python/shell 执行外部用户内容；运行环境限定到一次性目录，Secrets 仅从环境读取。
- 核查官方 session-log-deepseek 插件默认日志上传行为，基准实验显式关闭不必要的 session-log metadata 上传，并记录该配置；确认记录不会误入模型输入。
- 任何敏感原始请求/响应都需要脱敏与可选存储；.gitignore 覆盖 .env、token、workspace、原始大日志和临时文件。
- 限制重试次数、并发度与最大输出 token，默认串行运行以减少干扰，配置可复现。

### P0.3 四组缓存基准（计划 100 次有效 live 调用）

A — 连续 Session（25 次）：相同 Session 连续 25 个短任务，观察历史延长带来的命中趋势；标注与 B–D 非严格等长的混杂因素。

B — 相同前缀跨 Session（25 次）：每次新 Session，等长公共前缀与相同任务；衡量跨 Session 前缀复用。

C — 相同前缀 + 变化后缀（25 次）：每次新 Session，公共前缀完全相同，改变等长任务后缀，衡量公共前缀的缓存稳定性。

D — 变化的 Prompt 前缀（25 次）：每次新 Session，改变靠前 Prompt 内容，保持任务后缀与长度尽量恒定，检验前缀改变的损失。

每组固定：模型 id、推理力度、max_tokens、tool schema、配置、并发、地区/时间段、输入长度等级；除实验自变量外不允许变更。用明确且不同的 session ID（A 组同一 ID）。不同组执行顺序必须记录；如可行轮换/交错分组以避免时间漂移。每次运行记录条件标签、配置哈希、Session ID（脱敏）、调用时间。若 in-history prompt update 无法通过 SDK 公共接口测量，列为额外机制实验，不得把 D 组说成该功能已验证。

说明：100 次是目标有效调用数量，不是允许无限额外重试。实际成功数不足，报告 PARTIAL；不可用虚构或离线数据填满。

### P0.4 Token 统计、费用、失效与预算门控

必须从 DeepSeek-Harness 记录的 provider usage 对应到这些互斥桶：
- uncached_input_tokens（adapter 的 inputTokens，不是总 prompt）
- cache_read_tokens
- cache_write_tokens（如上游返回）
- output_tokens
- total_prompt_tokens = uncached + cache_read + cache_write
- cache_hit_rate = cache_read / total_prompt_tokens，分母 0 或缺字段记 unavailable

重要：上游 TokenUsage 的 inputTokens 与 cacheReadTokens / cacheWriteTokens 互斥，不能只用 inputTokens 作缓存分母，也不能重复计算 cacheRead。usage 为累计流时只取最终 settled usage，不应对分片累计求和；重试、失败 attempt 需单独计量，禁止忽略消耗。

实时从官方价格表记录日期、币种与命中/未命中/输出单价；不支持区分 cache-write 计价时要明确披露并给出上界，不得擅自等同于 cache-hit。计算 CNY 成本并与账单（如果能安全取得）抽样对账。不得硬编码永久性价格。

预算：用户当前授权本阶段 API 花费最多 ¥10（是实验上限，不是必须花完）。默认最大 100 个有效调用、输出上限 <=256 tokens/请求，串行执行，预先估计新请求在缓存全失效及上限输出/允许重试情况下的最坏账单；如将突破剩余预算，拒绝新请求并安全退出。由于账单更新可能延迟，不能宣传绝对不超支。丢失 usage、价格或计量不一致时 fail-closed 停止后续 live 调用，并保留已发生的实际成本或未知费用标记。任何预算提高需用户另行明确批准。

### P0.5 交付件

- benchmarks/cache_benchmark.py（或等价可运行 CLI）： --dry-run 默认、--live 显式开关、 --calls、--max-cny、--output-dir；启动前输出配置和安全预检。
- configs/cache_benchmark.yaml：模型、前缀、各组配额、调用参数、停机阈值。
- src/causalevo/usage.py：互斥 Token 桶、retry accounting、命中率、成本统计。
- tests/：至少覆盖 4 种场景分配、session ID 生成、usage 解析、重试/累计分片不重复计费、缺失数据 fail-closed、成本门限、密钥/日志脱敏、工具禁用与 Prompt 前缀确定性。
- docs/PHASE0_AUDIT.md：来源对应上游 SHA、主要机制及风险。
- docs/PHASE0_RESULTS.md：离线与真实 API 两种结果严格区分，真实部分无证据则写 NOT_RUN / BLOCKED。
- results/phase0/summary.json、calls.csv（真实 API 调用后生成；不得提交敏感完整请求响应）、实验配置快照、必要脱敏证据；明确哪些文件可安全提交。
- planner/executor_report.md：每个任务 PASS / PARTIAL / BLOCKED，证据路径，测试命令，运行次数、Token 总数、缓存命中率、估算人民币费用、失败和重试次数、缺陷列表。
- status.json：按 planner/WORKFLOW.md 协议更新执行状态。

### P0.6 验收 Gate（Planner 判定，Executor 不得自行认定最终 ACCEPTED）

G1：可复现的环境安装和固定版本，实际校验上游 SHA。
G2：无凭据可运行离线 dry-run+测试，测试结果真实、有失败注入。
G3：Shell 和其他工具确实不可由基准 Agent 调用；workspace / DSH_HOME 隔离。
G4：API Key 不落盘、不提交；用量桶与上游类型一致，预算故障 fail-closed。
G5：配置明确的四组实验均有固定任务生成器，标注 A 组的历史长度混杂。
G6：具备 live 凭据时达到最多 100 次有效调用并有逐次证据；无凭据时允许工程交付 PARTIAL，但不能标为 live-complete。
G7：主分支 origin/main 与 HEAD 一致、工作区 clean、测试报告与远端文件一致。
G8：禁止声称缓存优化已使成本下降或因果进化已显著有效，除非有实测及匹配对照。

## 2. GitHub 协议和完成动作

1. 启动先运行 git fetch origin，读取 main、planner/latest_plan.md、status.json，并检查既有文件；不得覆盖其他人的修改。
2. 在 main 上实施本计划；如果上游并发提交导致冲突，先合并/复核，禁止强推。
3. 每完成一个子任务可有局部提交，最后统一更新 docs/PHASE0_RESULTS.md、planner/executor_report.md、status.json。
4. 在结果中区分工程完成度与 live API 测量完成度，真实 live 验证缺失时设置 phase_status=BLOCKED 或 PARTIAL，不得伪造数字。
5. 最终 git push origin main；验证远端 SHA、工作树 clean、全部相关测试，向用户报告 Commit SHA、测试结果、真实花费与阻塞项。
6. 停止在 Phase 0，等待 GPT Planner 评审与下一份 planner/latest_plan.md；不要自行实施 Phase 1。

## 3. 下一阶段入门条件

只有 Planner 审核通过 G1–G5 且明确说明 G6 的完成/阻塞状态后，才可规划 Phase 1。Phase 1 将涉及任务执行与基线比较；本轮不实现反事实自进化核心。
