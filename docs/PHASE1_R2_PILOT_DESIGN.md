# Phase 1 R2 — SWE-bench Verified 可行性核对与 Pilot 设计

日期：2026-10-13。对应计划 CE-DSH-P1-R2（`planner/latest_plan.md`）的 P1R2-S4。关联文档：`docs/PHASE1_BENCHMARK_DECISION.md`、`benchmarks/registry.json`。

**范围声明：本文件仅为测量方案与保守预算评估。撰写过程中未下载任何 SWE-bench 数据集或镜像，未运行任何 SWE-bench 实例，未发送任何真实模型请求（本轮 live API 预算 ¥0）。所有未在本机亲验的字段一律标记 NOT_VERIFIED 或注明为估计/转述，不以估计冒充实测。任何 live pilot 均需用户另行明确授权（`require_live_authorization()` 机制：`DEEPSEEK_API_KEY` + `CE_DSH_LIVE_AUTH=phase1-pilot` 缺一不可）。**

## 1. 技术可行性核对表

| 项目 | 内容 | 状态 | 依据 |
|---|---|---|---|
| 数据集规模与构成 | SWE-bench Verified = 500 个人工核验实例，HF 数据集 `princeton-nlp/SWE-bench_Verified` | NOT_VERIFIED（元数据级） | `benchmarks/registry.json` / `docs/PHASE1_BENCHMARK_DECISION.md` 2026-10-10 元数据审计；未下载 |
| HF 数据访问 | 2026-10-13 本机无法访问 HF datasets-server（网络受限） | NOT_VERIFIED | 本机网络环境限制；需在网络可用环境重试或走镜像/离线包 |
| 许可证 | 仓库 MIT（GitHub license API 2026-10-10）；HF dataset card | VERIFIED（仓库级元数据） | `benchmarks/registry.json`；HF 数据集条款再分发前需复核（NOT_VERIFIED） |
| 官方评测 CLI/harness | `swebench` Python 包 + Docker harness，隐藏测试确定性 pass/fail | NOT_VERIFIED | 上游公开描述；本机未安装、未核验版本与 API 变动 |
| 官方 per-instance 镜像构建 | 完整构建集约 ~120GB 磁盘 | NOT_VERIFIED | 上游公开描述，未实测 |
| 第三方公开镜像 | `ghcr.io/epoch-research/swe-bench.eval.x86_64.<instance>` 镜像模式（第三方发布，MIT 声称） | NOT_VERIFIED | 第三方 registry，许可证与完整性待核实；核实前不批量拉取 |
| 本机 Docker 运行环境 | Docker daemon 可用；本地已有 `causalevo-dsh-agent:0.1.0`、`python:3.11-slim` | VERIFIED | 本机 2026-10-10 起多次实测（容器桥接探针、judge 执行） |
| 离线可复制性 | 数据集/镜像下载后可离线运行 | NOT_VERIFIED | 上游描述成立的前提是先完成一次性下载；当前网络受限未能验证 |
| 资源估算（单实例） | 镜像 3–8GB、单实例评测 CPU 5–30 分钟（保守区间） | NOT_VERIFIED（估计） | 依据上游镜像含完整 conda 环境及公开运行报告推断，见 §2 表注 |
| 污染风险 | 实例源自公开 GitHub issue，污染风险高；2026 年有 OpenAI 退役 SWE-bench Verified 的公开讨论（污染问题） | 转述 | 该讨论为公开报道的转述，未亲验原文；结论仅作为污染风险的旁证，不据此调整任何数字 |

缓解措施沿用 `docs/PHASE1_BENCHMARK_DECISION.md` §5：外部基准的 sealed/held-out 部分只用于评估，绝不进入 prompt/skill/tool 的调参与自进化回路；split 信息对策略盲化。

## 2. Pilot 实例候选

以下来自文献中常用于 agent 评测演示的实例。**标注：文献来源，本机未实测；选择理由是仓库成熟、测试套件为 pytest 体系、与本项目 executor/judge 管线匹配，不代表已验证可运行。**

| instance id | 仓库 | 预估 CPU（单实例评测） | 预估磁盘（镜像） | 预估端到端时间 | 依据 |
|---|---|---|---|---|---|
| astropy__astropy-12907 | astropy/astropy | 10–30 min | 4–8 GB | 15–40 min | 科学计算库测试套件较大；文献常用 pilot 实例 |
| astropy__astropy-13236 | astropy/astropy | 10–30 min | 4–8 GB | 15–40 min | 同上（镜像可与上条共用基础层） |
| django__django-13158 | django/django | 10–30 min | 4–8 GB | 15–40 min | django 全套测试运行慢，公开报告普遍为该量级 |
| sympy__sympy-18199 | sympy/sympy | 5–20 min | 3–6 GB | 10–30 min | 纯 Python 符号库，环境相对轻 |

表注：以上 CPU/磁盘/时间全部为保守估计，依据为上游"镜像含完整 conda 环境"的公开描述与公开的实例运行报告量级，**非本机实测**；第 5 个候选实例留待 smoke 后按实测资源占用补充。agent 侧 wall-time 由 `RuntimeBudget.wall_time_s` 硬切断，与评测测试耗时分开计量。

## 3. 等成本 B0/B1 实验矩阵

### 3.1 阶段划分

- **Stage 0（smoke，3–5 实例）**：从 §2 候选中取 3–5 个实例，B0/B1 各 1 次、单一固定 seed。目的不是产出任何成功率数字，而是验证管线跑通并做 floor effect 检查（见 §5）。任一侧全 0 或全部 budget_stop 时停止并上报，不进入 Stage 1。
- **Stage 1（pilot 主体，20–30 实例）**：实例清单在 smoke 通过后冻结；B0/B1 × 2–3 个 paired seeds。

### 3.2 配对与固定规则

- **等成本**：B0 与 B1 使用完全相同的 `RuntimeBudget` 参数（max_provider_calls、计费 token 桶、输出 token、tool calls、wall_time）；B1 的 reflection/reattempt 从同一额度扣除（计划 P1R2-S2 既定约束）。
- **paired seeds**：seed 集合事先固定并写入 config（例如 3 个固定整数值），同一 (instance, seed) 组合下 B0/B1 配对执行；seed 只控制我方可控的采样参数。
- **执行顺序**：(instance, policy, seed) 三元组顺序在运行前以固定 split_seed 打乱一次并记录到 manifest，之后不再变动；避免缓存预热等顺序混杂系统地偏向某一 policy。
- **记录**：run manifest 固定仓库 SHA、镜像 digest、任务包 hash、有效配置 hash、provider/model、timestamp、seed（P1R2-S3 既定）。

### 3.3 统计方法

- 每 (instance, policy, seed) 产出二值结果（独立 judge 的 sealed 判定，pass/fail）。
- **主分析：McNemar 配对检验**。对每个 (instance, seed) 对，B0/B1 配对后统计不一致对：b = B0 成功且 B1 失败的对数，c = B1 成功且 B0 失败的对数。成功率差值的置信区间通过对不一致比例 c/(b+c) 作精确二项（Clopper-Pearson）区间再变换得到；不一致对数少（预计 < 25）时**必须使用精确法**，不用渐近卡方。
- 同时报告各 arm 的边际成功率及 Wilson 区间，仅作描述，不作不配对显著性推断。
- 多 seed 时以 seed 为分层因素做分层/合并的敏感性检查；任何"剔除某 seed 后结论翻转"的情况必须如实报告。
- **provider 随机性声明（不可控因素）**：DeepSeek 官方未承诺按 seed 可复现的采样（NOT_VERIFIED）；温度等解码参数在我方固定，但服务端漂移、模型版本更新、负载相关的非确定性不受控。paired seed 只能对齐我方输入，不能消除 provider 端随机性；因此 pilot 只报告区间与效应方向，不作任何确定性因果断言，结论以"工程证据"口径表述。

## 4. 保守预算估算（全部为前提假设估算）

### 4.1 费率依据

费率取自 `src/causalevo/pricing.py` 的价格快照（DeepSeek 官方定价页，抓取日期 2026-10-10；模型 deepseek-flash = DeepSeek-V4.1-Flash；USD/CNY=7.10 为记录于 2026-10-10 的估算汇率），并经 Phase 0 真实小额运行交叉验证（`results/phase0/live/summary.json`：100 次调用，peak 口径 ¥0.0921、tiered 口径 ¥0.0460，平台扣费差额 ¥0.00，billing may lag）。

| 类别 | peak (USD/1M) | off-peak (USD/1M) | peak (¥/1M) | off-peak (¥/1M) |
|---|---|---|---|---|
| 输入 cache miss | 0.30 | 0.15 | 2.13 | 1.065 |
| 输入 cache hit | 0.006 | 0.003 | 0.0426 | 0.0213 |
| 输出 | 1.20 | 0.60 | 8.52 | 4.26 |

### 4.2 每任务成本上界（保守假设）

假设（全部为保守前提假设，非实测）：每任务最多 **2 次 provider 调用**；每次调用 **输入 8192 tokens 且全部按 cache miss 计**、**输出 2048 tokens**。

- 单次调用 peak：8192×0.30 + 2048×1.20 = 0.0049152 USD ≈ **¥0.0349**
- 每任务（2 调用）peak 上界：**¥0.0698**；off-peak 上界：**¥0.0349**

注意：Phase 0 实测 100 次调用合计仅 ¥0.0921（peak 口径），因为真实输出远小于 2048 且有缓存命中；本包络刻意保守。另按 P1R2-S3 既定警告：输出 cap=2048 是 Phase 1-R1 的静态包络，真实 SWE 编程任务（多文件定位、长补丁）**很可能超出 8k 输入/2048 输出假设**；任何预算变更须先同口径修改 B0/B1 并记录原始/更新配置，不得为单方成绩单独加预算。

### 4.3 场景汇总（全部为前提假设估算）

| 场景 | 运行数 | peak 上界 | off-peak 上界 |
|---|---|---|---|
| 26 microtasks，B0+B1，单 seed | 52 | ¥3.63 | ¥1.81 |
| 26 microtasks，B0+B1，2 seeds | 104 | ¥7.26 | ¥3.63 |
| SWE smoke：5 实例 × B0/B1 × 1 seed | 10 | ¥0.70 | ¥0.35 |
| SWE pilot：30 实例 × B0/B1 × 2 seeds | 120 | ¥8.38 | ¥4.19 |
| SWE pilot：30 实例 × B0/B1 × 3 seeds | 180 | ¥12.56 | ¥6.28 |

镜像/磁盘成本：smoke 5 实例按 §2 估计约 20–40GB（NOT_VERIFIED）；30 实例 pilot 预计 100GB 量级，接近官方完整构建集的 ~120GB 口径，须在网络与磁盘条件确认后再授权下载。

## 5. Floor effect 防护

- Stage 0 smoke 先于任何正式 pilot：若 B0、B1 成功率同时为 0，或大量 run 以 budget_stop / timeout 结束而无有效最终补丁，判定存在 floor effect 风险，**停止扩展并上报 Planner**，不得扩大样本硬跑。
- smoke 中逐 run 检查 finish_reason 分布与 ledger（provider_attempts、output_tokens、budget_stop_reason），区分"模型不会做"与"预算/协议问题导致的全 0"；后者是工程问题，先修管线再谈测量。
- 若 2048 输出 cap 导致普遍截断（max-tokens 比例畸高），按 §4.2 的同口径预算变更流程处理并完整记录，不静默调参。
- 实例难度梯度（文献报告的已解决率区间、补丁大小、上下文长度）在 pilot 冻结前记录备查，选例时刻意覆盖易/中档，避免全选难题造成结构性全 0。

## 6. 边界声明

本文件只是方案：未发送任何真实模型请求，未下载任何 SWE-bench 数据或镜像，无任何成功率数字。执行 Stage 0/1 需要用户单独发放 Phase 1 live 授权与预算，并经 Planner 发布后续计划；`require_live_authorization()` 之外的任何 live 调用路径都视为违规。第三方镜像（ghcr.io epoch-research）与 HF 数据集条款核实完成前，不得批量拉取或再分发。
