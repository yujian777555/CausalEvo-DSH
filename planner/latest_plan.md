# CausalEvo-DSH — Phase 1 / Round 1 正式执行规划

- Plan ID：CE-DSH-P1-R1
- 发布：2026-10-10
- GitHub 仓库：https://github.com/yujian777555/CausalEvo-DSH
- 分支：main
- Planner：GPT；Executor：Kimi
- 当前阶段：**Phase 1 — Objective Agent Benchmark + Fixed Harness Baselines**
- 初始状态：PLANNED；本轮在全部离线工程交付完成后停下，等待 Planner 验收。
- 基线：Phase 0 final Executor HEAD a7baa8979fb72860ad070f5e66ddf6d949cc0962。
- Phase 0 最终 ACCEPTED 记录：planner/reviews/CE-DSH-P0-R1.2-final.md。

## 0. 本阶段的科研定位

论文核心问题：黑盒 LLM Agent 自进化时，能否从失败轨迹中构造可检验的失败机制假设，通过受控干预和配对重放选择使**未见任务**受益的系统级改动？Phase 1 只提供客观、可复现的评测环境与强基线，不实现、不宣称任何 CausalEvo 提升。

基础模型：DeepSeek-Flash API，固定模型别名/请求参数与运行时间元数据；主执行框架 DeepSeek-Harness，采用非侵入式 SDK/插件适配，避免重造执行框架。计量继承 Phase 0，prompt 缓存和模型回答质量分开报告。

**授权边界：Phase 1 本轮仅授权无成本的离线环境开发、fake/replay 测试与公开基准元数据审计。新的 live API 预算 = 0 CNY。禁止调用任何付费模型或将 Phase 0 的 ¥10 视为本阶段可用预算；若后续需要 DeepSeek API 实验，应停在预算 Gate 并由用户明确授权后再发布新的 Planner 计划。**

## 1. P1.1 Benchmark 审核和任务分层（必做）

创建 `docs/PHASE1_BENCHMARK_DECISION.md` 和机器可读 `benchmarks/registry.json`。至少评估三种具有客观验证器的公开 Agent Benchmark 适配路径，例如 SWE-bench Verified 类代码修复、Terminal-Bench 类终端任务、AppWorld 类工具/API 任务（这些只是候选，不等于已验证可用）；针对以下指标选择 1 个作为论文主基准候选：

- benchmark 来源/许可证/版本/固定 commit 或 checksum、任务划分许可；
- 是否能在用户 Windows / Docker 环境离线、可复制地运行；是否需额外付费服务；
- 正确性是否有可执行 objective oracle，不以模型主观评分为主；
- 单任务典型工具回合、依赖大小、运行时间、安全风险、可复现难度；
- 能否构造已见训练/开发集、独立验证集与密封未见测试集；
- 与模型训练语料/公开答案污染风险及处理措施。

不可擅自报告尚未运行的外部 Benchmark 成功率。外部基准如不可下载或许可证不明，标记 BLOCKED/NOT_VERIFIED，给出后续步骤，不得伪造任务包。

为验证工程管线，另建立 **至少 24 个本地小型、确定性、无网络的 Python 修复任务**（只用于工程 smoke，不作为论文 SOTA 性能证据），具有可运行入口、预置 bug、可执行 oracle、独立 workspace 和 hash 固定；建议固定 12 train / 6 dev / 6 sealed test，随机分配一次并保存 seed。对同一类 bug 的近似重复和模板泄漏进行去重审计；train/dev/test 的任务目录隔离，不提供 sealed oracle 给模型。

## 2. P1.2 DeepSeek-Harness 工具型执行器（安全 P0）

Phase 0 的 `dsh_bench_patch.yml` 禁止全部工具，不能原样用于任务执行。新增用于 Phase 1 的 **独立最小权限工具 profile**，在真实 Host 与工作空间之间提供清晰隔离：

- 优先使用一次性 Linux Docker 容器作任务 executor，明确网络默认禁用、非 root、只挂载每任务独立目录、内存/CPU/pids/时间/磁盘上限、运行后自动销毁；Windows 上通过 Docker Desktop/WSL2 使用。若不可用，fake/replay 路径仍需正常工作，但真实命令执行标记 BLOCKED，**不可退化为宿主机无限权限 PowerShell**。
- 只暴露任务所需的固定、版本化 Tool Schema；不把 API Key 或其他秘密传入候选代码执行环境；模型仅访问允许目录，禁止访问宿主/其他任务数据、sealed tests、系统凭据。
- Harness SDK 维持 Session events/trajectory 与原始请求用量桶的可审计映射。每任务开始前独立 seed/snapshot，任务结束后容器/进程完全重置。
- 保持 Prompt、工具名称/签名/顺序稳定以便做缓存比较，但不能牺牲评测隔离来提高 cache hit。Run manifest 必须记录 provider/model、SDK、patch hash、任务环境镜像 digest、repo commit、config fingerprint。
- 引入环境隔离测试：路径越界、网络尝试、跨任务污染、隐藏测试泄漏、危险命令、资源耗尽、超时、日志敏感数据回显。不能只测试 prompt“不要访问”。

## 3. P1.3 任务执行、独立 Judge 与客观成功指标

增加 `src/causalevo/eval/`（task_spec、workspace_factory、executor、judge、trace、metrics 等实现可按项目结构调整）：

- 每任务包含 task_id、instructions、workspace image/digest、visible checks、sealed hidden evaluator reference、预期接口、超时与成本上限。
- Judge 在 Agent 结束且沙箱隔离完成之后独立运行，读取候选修改并执行确定性测试。公开给模型的 visible tests 与私有 sealed tests 物理/权限隔离，不将后者的断言或判分信息反馈到后续训练会话。
- 把状态分开：API response observed / tool call executed / task completed / visible tests passed / sealed tests passed / invalid / timeout / budget stop。单纯 finish_reason=completed、JSON 格式正确或模型自称修好均不算任务成功。
- 全程收集：任务成功率、partial tests、API attempts、input cache hit/miss、reasoning/output、估计 API 费、工具调用次数、容器耗时、API 延迟、失败类型、轨迹大小。失败时也必须保存明确证据；未知费用字段不能写 0。
- 轨迹保存需可重放、去敏且保留因果实验所必需的状态；原始敏感工具输出不要无条件提交公开仓库。推荐以 trace_id + run manifest + redacted events + task snapshot digest 组织。

## 4. P1.4 固定 Baseline（只有定义与离线 fake/replay 测试）

实现并版本化至少两套 baseline policy：
- B0：Fixed Harness Agent —— 固定 system prompt、固定工具目录与固定执行预算，遇失败不持久更新 Prompt/Skill/Tool。
- B1：Self-Reflection/Reattempt —— 在同一有限预算内允许一次结构化复盘/再尝试，但仍不跨任务修改 Agent 组件；与 B0 在 **总 token/最大 API 调用/最大工具调用/时间上限** 中采用相同预算上界，避免“多想一次自然更贵”不公平比较。

若已有可复现公开强基线实现，记录外部版本与对齐情况；本轮不借外部声称结果。未来反事实自进化方法必须用相同 Harness profile 和相同预算与这些基线对比。

固定种子与 paired-task 执行顺序（防止环境差异），为 B0/B1 留独立 run_id 和 workspace。数据划分和 judge 对策略盲化。Baseline configs 和测试覆盖：同任务同随机性控制、B0 不持久改变、B1 不能越预算、跨任务无状态泄漏。

## 5. P1.5 上一阶段的遗留风险门（不可省略）

- RISK-1：`assistant/attempt` 若无唯一 request id，重复等量 usage 可能对应真实不同请求。修复身份认证/事件指纹或在不明时保守标记 UNKNOWN_COST+STOP；**Phase 1 如需 live 重试/多步 Agent，必须先通过专门失败注入测试、Planner 复审**。当前离线 fake 默认禁止自动重试。
- RISK-2：多步 API 请求不能把「内部失败后重试」和「外层策略重新执行」混为同一种 attempt；每条 provider 计费请求须唯一计量，未计量请求不可悄然设零。
- RISK-3：配对任务重放须真正重新创建容器并重置文件状态/随机种子；Harness session replay 单独不足以构成反事实环境重放。
- RISK-4：模型动态别名的版本漂移、推理随机性与短 token cap 截断需要显式记录，不能将 API 观测成功视为任务成功。
- RISK-5：Benchmark 污染/隐性测试泄漏必须排查，特别是 dev/test 与反事实候选的交叉使用。
- RISK-6：实时预算 gate 用清晰的单任务/全局约束，Phase 1 live 默认为关闭；任何后续预算提升必须得到用户明确授权。

## 6. 本轮必须交付的工程件

1. `docs/PHASE1_BENCHMARK_DECISION.md`：至少 3 个候选基准的证据比较、许可证与选择依据。
2. `benchmarks/registry.json` + `benchmarks/tasks/`：24 个离线可验证 microtasks，固定 split、seed、文件/环境 hash、目录权限约束。
3. `src/causalevo/eval/` + `configs/phase1_*.yaml`：可复现任务执行、独立 judge、B0/B1、offline fake/replay 入口。
4. `tests/`：覆盖任务划分、hidden-test 隔离、环境重置、timeout、资源限制、政策对齐、输出正确性、成本统计与失败重试边界。至少新增 20 个有意义自动化测试，且原 Phase 0 回归必须持续全绿；不得凭数量代替场景质量。
5. `results/phase1/offline/`：离线 workflow 报告，分别记 requested/executed/scored counts，不能因 fake Runner 生成的合成答案错误而虚称 24/24 任务成功。
6. `docs/PHASE1_DESIGN.md`、`docs/PHASE1_RESULTS.md`、`planner/executor_report.md`、`status.json`。
7. 安装/运行命令（优先 Windows+Docker，兼顾 Linux），以及所有官方与第三方依赖的固定 SHA/版本。

## 7. Planner 验收 Gates

P1-G1：工程 smoke 的每个任务均有独立客观 judge 和隔离环境；任务清单固定且可复查，不把合成任务说成论文外部 Benchmark。
P1-G2：工具真实权限限定于隔离 workspace；容器/网络/隐藏测试隔离通过对抗性测试，不能动宿主机。
P1-G3：B0/B1 的决策政策与公平预算边界明确、锁定、具单元测试。
P1-G4：离线 24 任务 x 2 baseline 的执行调度跑通；必须分开“执行成功”和“任务通过率”，不要求 fake 模型一定修好任务。
P1-G5：全量 pytest（旧 79 回归 + 新测试）全绿，配置、镜像、task split、seed 与 manifest 可复现。
P1-G6：Phase 0 冻结原始 live CSV 未变，结果不被覆盖。
P1-G7：Phase 1 没有调用付费 API（本轮预算 = 0），未获得授权前任何代码不允许启动 live。
P1-G8：Commit + Push main，HEAD == origin/main、工作树 clean、证据与状态相符；Executor 不自行宣布 ACCEPTED。

## 8. 本轮停止条件与后续

Kimi 执行完成并提交后，将 status.json.phase_status 设置 READY_FOR_REVIEW，next_actor=GPT-Planner。暂不进入 Phase 1B 实际基线 API 评估，也不实施 Phase 2 失败机制诊断，更不开始 Prompt/Skill 自进化。Planner 会审查是否可安全运行真实 Agent，并根据用户明确批准的预算发布下一份 live pilot 计划。

执行时若遇到 Docker 不可用、公开 Benchmark 原始数据不可获取或许可/安全冲突，按 BLOCKED/PARTIAL 给出精确证据及最安全可运行子集，不要静默跳过安全要求、伪造数据或修改核心目标。
