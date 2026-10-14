# Phase 2.2 Diagnosis 结果（离线，零费用）

日期：2026-10-14。数据来源：已提交的 Phase 1 离线轨迹（fake provider / fake agent），**非真实模型性能证据**。

## 1. 数据集

- `results/phase2/diagnosis/diagnosis_dataset.jsonl`：124 行（每 trace 一行）；按 task_id 分组切分（seed=20261014）：train 78 / val 24 / test 22（见 dataset_manifest.json）。
- 标签来源：scenario_injected（构造性真值）、judge_outcome（success）、rule_chain_silver（仅训练）；评估仅用前两类，eval rows = 22。

## 2. Baseline 对比（val+test，n=22）

| 模型 | accuracy | macro F1 | unknown rate | ECE | evidence precision |
|---|---|---|---|---|---|
| B0-rules | 1.000 | 1.000 | 0.000 | 0.000 | 1.000 |
| B1-feature-lr | 1.000 | 1.000 | 0.000 | 0.019 | 1.000 |
| B2-embedding-lr | 1.000 | 1.000 | 0.000 | 0.019 | 1.000 |

**如实解读（不得外推）**：受控注入故障在该小样本上类间可分，全部模型满分只说明管线正确与类别可分离；不构成任何"诊断已解决"或模型能力结论。confusion matrix 见 results/phase2/diagnosis/confusion_matrix.json；risk-coverage 曲线在 baseline_results.json（本数据集所有模型在所有阈值下 coverage→accuracy 恒为 1.0，样本太小，无区分度）。

## 3. Abstention 机制验证

- 阈值 1.01 → 全部 unknown（测试锁定）；阈值 0 → 从不弃判。
- 当前数据无触发中间弃判；真实分布下的弃判行为待 live pilot 数据。

## 4. 产物

- dataset_manifest.json / baseline_results.json / confusion_matrix.json / sample_diagnosis.json / models/b1_feature_lr.pkl
- 再生成确定性测试：test_artifacts_regenerate_identically。

## 5. 限制

1. 标签主要来自注入故障与 judge 成功；真实失败分布未知。
2. 22 行评估集无统计功效；所有数字仅 sanity。
3. B2 哈希嵌入无语义先验。
4. 无 live 数据、无 holdout 使用、无 CoT 输入。
