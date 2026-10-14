# Phase 1.6 Benchmark Freeze — SWE-bench Verified

日期：2026-10-14。性质：可行性冻结审计。**未运行任何真实评估、未调用任何付费 API。**

## 1. 数据集身份与版本（已验证）

| 项 | 值 | 证据 |
|---|---|---|
| 数据集 | `princeton-nlp/SWE-bench_Verified`（HF） | HF API 经代理实测 2026-10-14 |
| 版本（revision SHA） | `c104f840cc67f8b6eec6f759ebc8b2693d585d4a` | HF API `sha` 字段 |
| lastModified | 2025-02-18 | HF API |
| 规模 | 500 实例 | datasets-server `num_rows_total` |
| 字段 | repo, instance_id, base_commit, patch, test_patch, problem_statement, hints_text, created_at, version, FAIL_TO_PASS, PASS_TO_PASS, environment_setup_commit, difficulty | datasets-server `features` |
| 许可证 | SWE-bench 代码仓 MIT（GitHub license API 2026-10-10）；HF 数据集 cardData 未声明 license | 两处如实区分；引用风险低但记录为"卡片未声明" |

## 2. 评估协议（官方 harness 对齐）

- 官方路径：`swebench.harness.run_evaluation`，Docker 容器内应用 patch、运行 FAIL_TO_PASS + PASS_TO_PASS，产出 resolved 判定。
- 本项目映射：judge 侧容器执行（与 Phase 1 的 DockerExecutor 一致），sealed 测试 = FAIL_TO_PASS/PASS_TO_PASS，Agent 不得接触；实例仓库在容器内 checkout 到 base_commit。
- 判定口径：成功 = 官方 harness resolved（全部 F2P 过且 P2P 不回归）。不得以模型自述代替。

## 3. Docker 环境（已验证可获取）

第三方公开镜像 registry（Epoch Research，宣称 MIT，声称 2290/2294 覆盖；第三方来源，已标注待复核）：
`ghcr.io/epoch-research/swe-bench.eval.x86_64.<instance>:latest`。

2026-10-14 经 `docker manifest inspect` 实测可解析（digest 已钉死）：

| 实例 | 镜像 digest | 状态 |
|---|---|---|
| astropy__astropy-12907 | `sha256:87fda8f3ae644b986737fad17ca1f05cc4ffdf4d9f11acd4ca70bae12674495c` | VERIFIED（manifest 存在） |
| django__django-13158 | `sha256:57f86769288206a13dd48b7b7e83af12749cfdff5e38c21a41e41690d437c9a1` | VERIFIED |
| sympy__sympy-18199 | `sha256:1564b39de0842073e2ec631b42473c10940dd94c6cd68de52e2f79489343b09c` | VERIFIED |
| astropy__astropy-13236 | `sha256:98ecd819c7c599075f8b267aea8b9a4a2df9a558e73e4fb42fd60eb742fe3a7c` | VERIFIED |

注意：manifest 可解析 ≠ 镜像已拉取并跑通 oracle；真正的环境验证是 pilot 前置 smoke（需要下载窗口，未执行）。

## 4. Pilot 实例选择标准（冻结）

入选标准：difficulty 字段 ≤ "1-4 hours"；patch ≤ 3000 字节（小修复面）；F2P ≤ 200（评测时间可控）；repo 在 astropy/django/sympy 等主流 Python 项目（环境镜像覆盖率高）。

已核实的候选（全部经 datasets-server 实测字段）：

| instance_id | repo | base_commit | version | patch bytes | F2P | P2P | env_commit | difficulty |
|---|---|---|---|---|---|---|---|---|
| astropy__astropy-12907 | astropy/astropy | d16bfe05a7 | 4.3 | 470 | 170 | 989 | 298ccb478e | 15 min – 1 hour |
| django__django-13158 | django/django | 7af8f41273 | 3.2 | 961 | 75 | 2569 | 65dfb06a1a | 15 min – 1 hour |
| sympy__sympy-18199 | sympy/sympy | ba80d1e493 | 1.6 | 2838 | 22 | 2668 | 28b41c73c1 | 1–4 hours |

第 4–5 个候选实例留待 smoke 后按同标准补齐（不在未见数据上预先调参）。

## 5. 可复现性哈希

- 数据集 revision：`c104f840cc67f8b6eec6f759ebc8b2693d585d4a`（HF）。
- 镜像 digest：见 §3 表。
- 实例选择标准：§4（冻结）。
- 任何实例列表变更：新增 dated 章节并记录理由。

## 6. 诚实边界

- HF 数据集**内容**（problem_statement 等）本机已可读（经代理），但**完整 500 行未全量校验**；逐实例字段以实际 pilot 下载时复核为准。
- Epoch 镜像为第三方重建，非官方 SWE-bench 组织产物；与官方 harness 的等价性未经本机验证（NOT_VERIFIED），pilot 前必须用 oracle patch 跑一次对照。
- 2026 年存在 OpenAI 退役 SWE-bench Verified 的公开讨论（污染担忧，转述来源）；本项目的污染缓解依赖 private holdout（见 PHASE1_6_EVAL_PROTOCOL.md §3），不仅靠外部基准。

## 7. 结论

**可行性：VERIFIED（数据+镜像可获取且已钉版本）**。环境端到端 smoke（镜像拉取 + oracle 评测）为 pilot 前置 Gate，未在本轮执行（无授权窗口）。
