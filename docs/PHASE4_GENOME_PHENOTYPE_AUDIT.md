# Genome/Phenotype 审计（P4-R1.1-S4）

日期：2026-10-14。证据：scripts/audit_genome_phenotype.py → results/phase4/audit/genome_phenotype_audit.json。

## 实测数字

- 基因型空间：144（2×2×3×2×2×3）。
- 唯一表型：**16**（duplicate ratio 0.8889）。
- 退化基因（翻任一值从不改变表型）：`reflection_step`、`retry_strategy`（标记 reserved）。
- 有效基因：`tool_validation`、`read_before_write`、`verification_level`、`stagnation_break`。
- `verification_level=1` 与 `=2` 表型相同（强度未实现）。

## 结论与处置

1. NSGA-III 的"搜索空间"名义 144，实际 16；Pareto 前沿出现的重复 fitness 向量来自不同 genome_id 的同表型个体 —— 已在 PHASE3_CEA_V1_RESULTS.md 口径内注明"重复表型"，现由本审计坐实。
2. 变异/交叉大多不产生新表型；缓存（FitnessCache 按 genome_id）不识别表型重复 → 未来版本应按表型哈希缓存以避免重复评估（记录为后续改进，不修改冻结的 3.2 代码路径）。
3. 不新增无证据的基因复杂度；reserved 基因保留但标注。
4. 一致性标识：表型元组即一致性 key；`genome.phenotype_transforms()` 输出为唯一事实源。

## 对历史结果的影响

Phase 3.2 结论（前沿权衡、基线对比）不受影响：它们基于实测表型。受影响的是"搜索空间大小"的表述 —— 已在本文件修正为 16 个唯一表型。
