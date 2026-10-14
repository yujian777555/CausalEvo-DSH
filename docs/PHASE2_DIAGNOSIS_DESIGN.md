# Phase 2.2 Diagnosis 设计（学习式失败诊断）

日期：2026-10-14。范围：Failure Diagnosis 系统设计与冻结边界。**不实现** intervention optimizer / evolution controller / RL / prompt evolution。

## 1. 架构

```
TaskTrace (Phase 1 轨迹，redacted)
    │
    ▼
FailureFeature 提取器 (src/causalevo/diagnosis/features.py)
    │  task: split / prompt_chars / n_visible_checks
    │  行为: tool_calls / provider_calls / action_diversity /
    │        failed_action_ratio / repeat_max_run / events_count
    │  错误: failure_kind / unknown_spend / budget_stop
    │  验证: edited_workspace / judge_invalid / visible/sealed pass
    ▼
Diagnosis Dataset (dataset.py, 按 task_id 分组切分, seed=20261014)
    ▼
诊断模型 → DiagnosisResult(failure_type, evidence[], confidence, abstained)
    ▼
CandidateIntervention 接口（仅结构，不执行）
```

## 2. 数据与标签

- 来源：`results/phase1/**/traces.jsonl`（已提交离线 run；fake provider / replay，无真实模型费用）。
- 标签来源分档（dataset row 的 `label_source`）：
  - `scenario_injected`：R2 场景注入故障（构造性 ground truth）
  - `judge_outcome`：judge 判定的 success
  - `rule_chain_silver`：Phase 2.1 冻结规则链的银标（distant supervision，仅训练用）
  - `unlabeled`：不进入监督
- 评分口径：`scenario_injected` + `judge_outcome`，silver 不进评估指标（scripts/run_diagnosis.py 的 EVAL_LABEL_SOURCES）。
- 防泄漏：按 task_id 分组切分（同一任务的轨迹只进一个 split）。

## 3. 三个 Baseline

| Baseline | 输入 | 模型 | 备注 |
|---|---|---|---|
| B0-rules | 完整 trace | Phase 2.1 冻结规则链 | 不训练 |
| B1-feature-lr | FailureFeature（数值+类别） | DictVectorizer + LogisticRegression | evidence = top-\|coef\| 特征（`feature:name=value`，附可解析的 trace ref；引用不存在即剔除） |
| B2-embedding-lr | slim 事件图文本化（结构 token，无正文） | FeatureHasher(1024) + LogisticRegression | 全离线哈希嵌入；未下载任何预训练模型（不需要） |

## 4. Abstention

`max class prob < threshold → unknown`。默认阈值 0.5；risk-coverage 曲线在 baseline_results.json 逐模型记录。禁止强迫分类。

## 5. Evidence attribution

- B0：规则证据（trace ref）。
- B1：top-特征 evidence，字段可回查（`feature:` 前缀对 row 可验证；`@ref` 指向 trace）。
- 评估：evidence_precision（引用真实存在比例）+ evidence coverage（每条诊断是否带证据）。
- 任何证据不得引用 CoT、sealed 内容、holdout。

## 6. 序列化与复现

- B1 模型 pickle 存 `results/phase2/diagnosis/models/b1_feature_lr.pkl`；round-trip 测试锁定。
- 全管线确定性：同输入同输出（test_artifacts_regenerate_identically）。
- 复现：`scripts/run_diagnosis.py`（离线，零费用）。

## 7. 限制

- 数据来自受控注入故障与工程 noop 运行；类别分离理想化，accuracy=1.0 仅为构造性 sanity check，**不是泛化能力**。
- 真实 SWE-bench 轨迹的失败分布、长上下文与多步工具交互未覆盖。
- B2 的哈希嵌入无语义先验；仅作结构信号基线。
