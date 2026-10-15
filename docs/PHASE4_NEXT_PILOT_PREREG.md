# 下一轮真实 Benchmark Pilot 预注册草案（P4-R1.1-S5，仅设计，零费用）

日期：2026-10-14。**未获用户新预算批准前不执行任何 live 调用。**

## 1. 范围

- 候选：SWE-bench Verified 的 3 个冻结 pilot 实例（见 docs/PHASE1_6_BENCHMARK_FREEZE.md：astropy__astropy-12907、django__django-13158、sympy__sympy-18199）。
- 前置 smoke：oracle/gold patch 在钉死 digest 的镜像中通过 → 否则 pilot BLOCKED（不下载大批镜像；先单实例）。
- 26 microtasks 仅工程回归，不作论文主结果。

## 2. 臂（预注册）

B0 单试、B1 随机干预（同包络）、B2 规则、B3 Reflexion、B4 CEA-v0（经 CausalPolicyAdapter 真实 LinUCB）、B5 CEA-v1（经 adapter 真实冻结 Pareto 基因组）。预算包络两臂一致并记录；live 经 budget proxy 逐请求门控。

## 3. 统计（预注册）

- 主对照：B5 vs B1（同重试额度）；B5 vs B0 仅辅助（retry 混杂已声明）。
- McNemar exact + task-level cluster bootstrap；效应量与 CI 同时报告；不以均值论英雄。
- 难度层在冻结标准内预选；不依据 CEA 结果挑样本。
- 探索性（microtask 规模试跑）与确认性（SWE pilot）分开标记。

## 4. 停止规则

- unknown_cost / budget_stop / 门控拒绝 → 全局 fail-closed。
- 数据质量门：invalid >10% 或 timeout >30% → 批次仅工程证据。

## 5. 预算草案（估算，需批准）

- 3 实例 × 6 臂 × 2 种子 × ≤2 attempts × ~4 LLM 请求 × (~4k in + 256 out) ≈ 上界 ¥1.5（peak 价）；申请额度建议 ¥3.0（2× 余量）。未批准 = 不执行。
