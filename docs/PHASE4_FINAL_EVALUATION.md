# Phase 4 最终评估报告（Real Agent Evolution Validation）

日期：2026-10-15。实验：真实 DeepSeek-Flash（deepseek-flash）+ 容器化 Harness + 独立 judge；26 microtasks × 6 臂 × 2 种子 = 312 run。**本轮真实 API 调用已发生并全部记录（见 §6）。**

## 1. Benchmark 与协议

- 任务：26 个本地 microtasks（工程 pilot 规模；非论文 unseen benchmark）。
- 协议：docs/PHASE4_EXPERIMENT_PROTOCOL.md（live 前冻结；2026-10-15 有一次口径澄清修订：provider 调用 vs agent attempt）。
- 数据：results/phase4/live/phase4-live-20261014T110259Z/（tasks.jsonl 312 行 + manifest + protocol + 三个分析文件）。

## 2. Baselines

B0 原始（无重试）、B1 随机干预、B2 规则干预、B3 Reflexion 式反思、B4 CEA-v0（LinUCB）、B5 CEA-v1（NSGA-III 前沿基因组策略包）。

## 3. 结果（pass rate = 最终成功/52）

| 臂 | pass rate | recovery rate（首败后恢复） | 成本 CNY |
|---|---|---|---|
| B0 original | 0.808 | —（无重试） | 0.123 |
| B1 random | **0.923** | 0.556 | 0.119 |
| B2 rule | 0.885 | 0.250 | 0.119 |
| B3 reflexion | 0.827 | 0.100 | 0.117 |
| B4 CEA-v0 | 0.846 | 0.111 | 0.118 |
| B5 CEA-v1 | 0.885 | 0.500 | 0.118 |

Evolution gain（B5−B0）= +7.7pp。

## 4. 统计显著性（配对，n=52 对）

| 比较 | McNemar p | bootstrap 95% CI（差值） |
|---|---|---|
| B5 vs B0 | 0.344 | [-0.038, +0.192] |
| B5 vs B1（随机对照，RQ3 关键） | 0.727 | [-0.154, +0.058] |
| B5 vs B4 | 0.727 | — |

**结论（诚实）**：本 pilot 规模上，B5（CEA-v1）相对 B0 的提升不具备统计显著性；相对随机干预无优势证据。CI 均跨 0。论文口径：平台与因果链端到端验证成立；算法优越性在此规模未证实。

## 5. 因果与消融

- 随机干预对照（B1）数值最高 —— 直接说明"有针对性的干预"在本任务集上没有可测优势；RQ3 的答案为"未能证明因果演化带来增益"。
- 消融映射：A1 无因果奖励=B4 训练口径变体（见 P3.1 A3/A4）；A2 无 NSGA-III=B4；A3 无诊断=B2；A4 无演化记忆=B4 不更新。各臂数字见 §3。
- 成本均摊每臂 ≈ ¥0.12（总 ¥0.715）："提升是否值得"——B5 的 0.885 相对 B0 的 0.808 需要重试成本；B1 的 0.923 反而更省（随机重试廉价）。如实记录。

## 6. API 使用与成本

- 调用：312 任务 run，per-arm provider_calls/token/cost 全记录（cost_analysis.json）。
- 总费用 ¥0.715（预算上限 ¥3.00，余额 ¥3.75 → 剩余 ¥3.03 可见）。无 unknown_cost 事件。
- 价格口径：价格页 2026-10-10 费率 + 逐次 tier；平台对账受分辨率限制（见 Phase 0 声明）。

## 7. 限制

1. microtasks 对真实模型偏易（B0 已 80.8%）——天花板压缩了改进空间；需要更难任务集（SWE-bench pilot）才能区分算法。
2. n=52 配对，检验功效低。
3. 干预指令为冻结文本；真实进化出的连续策略空间未在 live 覆盖。
4. 单模型、单地区、短窗口。

## 8. 对论文的意义

平台已能可审计地回答 RQ1–RQ4；当前答案：工程闭环成立，算法增益未证实（需更难基准与更大样本）。这是真实的负面/中性结果，不是失败：它定义了下一步（难任务 pilot）的必要性。
