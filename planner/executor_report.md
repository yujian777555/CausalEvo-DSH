# Executor Report — Phase 2.2 Failure Diagnosis Model（CE-DSH-P2.2）

日期：2026-10-14。Executor：Kimi。本轮零 DeepSeek API 调用、零费用；未触碰 Phase 0/1/1.6/2.1 冻结成果；未实现 intervention/evolution/RL。

## 交付项

| 项 | 状态 | 证据 |
|---|---|---|
| S1 FailureFeature 提取器 | PASS | src/causalevo/diagnosis/features.py（task/行为/错误/验证四组特征；无 CoT、无 sealed 内容、无 holdout） |
| S2 Diagnosis Dataset | PASS | dataset.py + results/phase2/diagnosis/diagnosis_dataset.jsonl（124 行；task_id 分组切分；seed=20261014；label_source 分档） |
| S3 三个 Baseline | PASS | B0 规则链（沿用 P2.1）、B1 DictVectorizer+LogReg（含序列化）、B2 哈希嵌入+LogReg（全离线，无需下载模型） |
| S4 Evidence attribution | PASS | B1 evidence=top-特征（`feature:name=value @ref`，ref 不存在即剔除）；evidence precision/coverage 进入评估 |
| S5 Unknown/Abstention | PASS | 置信阈值弃判；unknown rate、accuracy-after-abstention、risk-coverage 曲线入 baseline_results.json |
| S6 评估协议 | PASS | docs/PHASE2_DIAGNOSIS_RESULTS.md + 冻结口径（split、指标、calibration、abstention） |
| S7 Intervention 接口 | PASS | DiagnosisResult→CandidateIntervention（仅结构，序列化往返测试锁定） |
| 文档 | PASS | docs/PHASE2_DIAGNOSIS_DESIGN.md、PHASE2_DIAGNOSIS_RESULTS.md |
| 测试 | PASS | **261 passed / 0 failed / 0 skipped**（231 + 30 新增） |

## 结果（如实）

- eval rows=22（scenario_injected + judge_outcome 标签）；三个 baseline accuracy/macroF1 均 1.000 —— **构造性 sanity，非泛化能力**；B1/B2 ECE 0.019；无弃判触发。
- 产物：results/phase2/diagnosis/{dataset_manifest, baseline_results, confusion_matrix, sample_diagnosis, models/}。

## 事故与修复

- 特征 kwargs 不匹配（prompt_chars 键名）→ 修正。
- B1 evidence 初版盲目引用 trace 字段，在无 agent 块的旧 trace 上失效 → 改为可回查 feature 条目 + 引用解析过滤。
- split 泄漏测试初版误把"同 split 多 trace"当泄漏 → 修正为一致性校验。

## 停止

停在 Phase 2.2。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。
