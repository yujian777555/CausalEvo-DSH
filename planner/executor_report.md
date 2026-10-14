# Executor Report — Phase 2.1 Failure Attribution Foundation（CE-DSH-P2.1）

日期：2026-10-14。Executor：Kimi。本轮零 DeepSeek API 调用、零费用；Phase 0 / 1 / 1.5 / 1.6 冻结数据未触碰；未实现任何进化/RL/prompt-evolution 逻辑。

## 交付项

| 项 | 状态 | 证据 |
|---|---|---|
| S1 Failure Schema | PASS | docs/PHASE2_FAILURE_SCHEMA.md + src/causalevo/analysis/schema.py（唯一事实源；6 类 + unknown；evidence 只指轨迹字段，无 CoT） |
| S2 Trace Analyzer | PASS | src/causalevo/analysis/trace_analyzer.py（仅用可观测轨迹 + judge 结果；基础设施故障优先归 execution_failure） |
| S3 Failure Dataset Builder | PASS | src/causalevo/failure_dataset/builder.py；results/phase2/failure_analysis/（124 条记录，全部来自已提交真实离线 trace，零伪造；manifest/stats/sample_reports） |
| S4 基线 B0/B1 | PASS | src/causalevo/analysis/baselines.py：B0 outcome-only（大量弃判的地板线）、B1 规则链 |
| S5 评估协议 | PASS | docs/PHASE2_FAILURE_EVAL.md（accuracy/macro-F1/evidence coverage/unknown rate/abstention；允许 unknown；指标冻结） |
| S6 CounterfactualCase | PASS | 结构 + 校验 + 序列化往返测试；未实现任何重放优化 |
| 测试 | PASS | **231 passed / 0 failed / 0 skipped**（202 回归 + 29 新增：schema 11、analyzer 10、dataset 8） |

## Failure 数据集散点（真实 trace 派生）

- 124 条：planning 104（noop 轨迹）、execution 4、knowledge 3、tool 3、strategy 3、unknown 7。
- labeled 子集（场景注入 ground truth）accuracy = 1.0 —— 如实声明：这只说明规则链与注入故障对齐（构造性验证），**不是泛化准确率**；unknown_rate 5.6%。

## 纪律声明

- 无 chain-of-thought 作为证据；无 sealed/holdout 内容进入记录；无 API key 入产物（有测试扫描）。
- 未宣称 CausalEvo 提升；未运行任何重放实验。

## 停止

停在 Phase 2.1。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。
