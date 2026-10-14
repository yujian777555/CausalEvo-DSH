# Phase 3.2 CEA-v1 设计（多目标因果干预进化）

日期：2026-10-14。范围：在 CEA-v0（LinUCB 选择）之上引入**干预基因组 + NSGA-III 多目标进化搜索**。不宣称真实自进化成功；所有适应度来自反事实重放测量。

## 1. 为什么需要 evolutionary search

CEA-v0 只能在人工预定义的 7 个干预中选择。真实修复策略空间是组合的（校验×预读×自测×停滞检测×…），人工枚举不完备；进化搜索把"选哪个"升级为"组合出什么"。

## 2. 为什么 multi-objective

只最大化成功率会偏向"重"干预（更多步骤、更高成本、更脆）。论文口径下必须同时优化：success gain、成本、额外步数、鲁棒性（跨失败案例）。单目标会把工程权衡藏进任意权重——Pareto 前沿让权衡显式化。

## 3. 为什么 NSGA-III

目标数 = 4（>3 时 Pareto 排序拥挤度失效）；NSGA-III 的参考方向关联在小种群、多目标下比 NSGA-II 更均匀。纯 numpy 实现（无大型优化库依赖），确定性（seed 固定）。

## 4. Genome 表示

`InterventionGenome`：6 个基因（tool_validation、read_before_write、verification_level、stagnation_break、reflection_step、retry_strategy），表型 = 有序磁带变换管线（phenotype_transforms）。支持 serialize/mutate（按基因重采样）/crossover（均匀）/distance（归一化 Hamming）。

## 5. 流程

```
Population（规则种子 + 随机组合，含 parent 谱系）
  ↓ 对每个 genome：表型 → 磁带变换 → 容器重放（train 失败案例） → 4 目标 fitness
  ↓ NSGA-III：非支配排序 → 理想点/极端点归一化 → 参考方向关联 → niching 选择
  ↓ 均匀交叉 + 逐基因变异
  ↓ 下一代
最终 Pareto 前沿在 held-out 失败案例（wrong_fix）上做泛化评估。
```

## 6. 基线与消融

- B0 随机搜索（同评估预算）、B1 规则库（Phase 2.3 种子基因组）、B2 CEA-v0（LinUCB 策略映射回基因组）、B3 NSGA-III。
- A1 无变异（仅交叉）、A2 单目标（只 success gain）、A3 普通 outcome 奖励、A4 因果差值奖励。

## 7. 限制

1. 表型映射把基因压到少数离散变换——基因组空间大但表型空间小；结论限于机制验证。
2. 适应度测量自磁带模拟；非真实模型改善。
3. 种群 6 × 3 代，规模小；超体积参考点固定在 manifest。
4. 无 live 数据、无 holdout、无 CoT。
