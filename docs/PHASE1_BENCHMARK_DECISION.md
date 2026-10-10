# Phase 1 基准选择决策（Benchmark Decision）

日期：2026-10-10。对应计划 CE-DSH-P1-R1 的 P1.1。机器可读元数据见 `benchmarks/registry.json`。

**范围声明：本轮仅做公开元数据审计（GitHub license API 查询与公开资料，查询日期 2026-10-10），未下载、未安装、未运行任何外部基准，无任何外部基准成功率数字。所有未亲验字段标记 NOT_VERIFIED。**

## 1. 评估维度

依据 P1.1 要求，对每个候选基准考察：

- **来源/许可证/版本固定**：上游仓库、许可证（以 GitHub license API 查询日期为准）、任务数、版本或 commit/checksum 固定方式。
- **离线可复制运行**：能否在用户 Windows + Docker（Docker Desktop/WSL2）环境离线、确定性地运行；磁盘/镜像体积；是否需额外付费服务。
- **客观 oracle**：正确性是否由可执行的确定性测试/状态检查判定，而非模型主观评分。
- **成本**：数据是否免费；典型运行的算力与时间开销。
- **污染风险**：任务内容是否可能已进入模型训练语料（公开 GitHub issue/任务），及缓解措施。
- **split 许可**：能否构造已见 train/dev 与密封未见 test，且 sealed 仅用于评估。

## 2. 候选对比

| 维度 | SWE-bench Verified | Terminal-Bench (core/2.x) | AppWorld |
|---|---|---|---|
| 来源 | github.com/SWE-bench/SWE-bench + HF 数据集 `princeton-nlp/SWE-bench_Verified` | github.com/laude-institute/terminal-bench + harbor 框架 | github.com/StonyBrookNLP/appworld（ACL'24 best resource paper） |
| 许可证 | MIT（仓库，GitHub license API 2026-10-10；HF dataset card） | 原始为 MIT/Apache-2.0 双许可（第三方 NOTICE，2026-03）；但 GitHub license API 2026-10-10 返回 none，**再分发前必须复核** | Apache-2.0（GitHub license API 2026-10-10 确认） |
| 任务规模 | 500 任务 | 约 89（2.0）至 247（core），随版本变化 | 覆盖 457 APIs / 9 个模拟应用的任务 |
| 客观 oracle | 每实例隐藏测试套件，确定性 pass/fail，Docker harness | 每任务 Docker 镜像 + 程序化验证测试，存在 oracle 解 | 程序化状态检查（state-based tests，TGC 等） |
| 离线可复制 | 镜像/数据集下载后可离线；完整构建集约需 ~120GB 磁盘 | 拉取镜像后可离线；每任务独立容器 | 引擎本地运行；环境搭建较重 |
| 成本 | 数据免费；算力开销重 | 数据免费；算力中等 | 数据免费 |
| 污染风险 | 高（公开 GitHub issue 已进入训练语料）；缓解：sealed split 仅用于评估、绝不用于调参 | 中（任务公开）；仍需 sealed-split 纪律 | 中 |
| 本轮状态 | NOT_VERIFIED（仅元数据审计，未下载） | NOT_VERIFIED（仅元数据审计，未下载；许可证待复核） | NOT_VERIFIED（仅元数据审计，未下载） |

来源 URL：

- SWE-bench：https://github.com/SWE-bench/SWE-bench ；HF 数据集：https://huggingface.co/datasets/princeton-nlp/SWE-bench_Verified
- Terminal-Bench：https://github.com/laude-institute/terminal-bench
- AppWorld：https://github.com/StonyBrookNLP/appworld
- 许可证核对接口：GitHub Repos API `GET /repos/{owner}/{repo}/license`，查询日期 2026-10-10。

## 3. 选择

- **主基准候选：SWE-bench Verified**。理由：Docker harness 成熟且 oracle 为确定性隐藏测试；MIT 许可证明确；Python 仓库任务与本项目 executor/judge 管线直接匹配；社区采用度高，结果可比。
- **备选：AppWorld**。Apache-2.0 许可证已经 API 确认，提供工具/API 多样性，用于覆盖代码修复之外的 agent 场景。
- **Terminal-Bench：许可证待复核**。GitHub license API 2026-10-10 未检出许可证，与第三方 NOTICE（2026-03，MIT/Apache-2.0 双许可）记录不一致；复核完成前不下载、不再分发。
- 决策状态：候选已选定用于 Phase 1B pilot 规划；本轮未下载、未运行任何外部基准。任何外部基准的实际接入均需另经 Planner 复审与用户授权。

## 4. 本轮工作边界

- 仅元数据审计：证据来源为 GitHub license API（2026-10-10 查询）与上述公开页面。
- 未下载任何外部数据集/镜像，未运行任何外部基准任务，无外部基准成功率数字。
- 未亲验的字段（任务数随版本变化、磁盘占用实测值、实际运行时长等）一律按上游公开描述引用或标记 NOT_VERIFIED，不以估计冒充实测。

## 5. 污染与 split 策略

- SWE-bench Verified 任务源自公开 GitHub issue，污染风险为高；因此外部基准的 sealed/held-out 部分**只用于评估**，绝不进入 Prompt/Skill/Tool 的调参或自进化更新回路。
- 数据划分对策略盲化：judge 与 split 信息不反馈到后续训练会话；sealed 测试的断言与判分细节不进入模型可见上下文。
- 任何「同一任务既用于开发又用于评估」的交叉使用（dev/test 与反事实候选之间）必须显式排查并记录（对应计划 RISK-5）。

## 6. 本地 26 个 microtasks 的定位

`benchmarks/tasks/` 下 26 个确定性 Python 修复 microtask（split seed 20261010，train 13 / dev 7 / sealed_test 6，清单与 hash 见 `benchmarks/registry.json`）**仅用于工程 smoke**：验证 task 加载、workspace 隔离、executor、独立 judge、trace/metrics 管线跑通。它们不是论文的外部基准性能证据，不得据此宣称任何模型能力或方法收益。
