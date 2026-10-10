# Planner Review — CE-DSH-P0-R1（审计提交 dc056ea）

日期：2026-10-10
审查结论：**CHANGES_REQUESTED（Phase 0 暂不最终 ACCEPTED）**
新修复计划：`planner/latest_plan.md`，ID `CE-DSH-P0-R1.1`
来源：GitHub origin/main @ dc056ea0cb210bf976e1b9f105be5fa2103c1863，源代码、status.json、报告、results/phase0/live/calls.csv 与 summary.json。**没有在 Planner 环境本地重跑 pytest，也没有独立读取 API 提供商后台调用记录。**

## 一、已通过的独立检查

- GitHub main HEAD = dc056ea...；树中存在 Phase 0 各项报告/代码/CSV/测试。
- committed live/calls.csv 100 行，A/B/C/D 各 25，100 条 status=ok，全部包含可解析的 usage 桶、计费字段，0 记录带 retry；数据的每行 input = uncached + cache_read（cache_write 未上报）。
- CSV 加总费用 off_peak = ¥0.0460417392；summary.json 组级费用合计 ¥0.046042，吻合四舍五入；没有发现明显的成本超限。
- 官方 Harness 相关说明有具体上游 SHA 与 SDK 版本，配置补丁显式禁用已知工具项，报告声称 runtime no-tools dump 与 live smoke 通过；工具禁用的**真实 runtime 证明来自 Executor 报告，Planner 未亲自运行。**
- 关键混杂已披露（A 历史增长、D 仅前缀变化、短时间集中观测）；没有假称因果进化显著有效。

## 二、阻断问题（附独立计算）

### R1 — 审计报告/状态总体 token 数错误

从 `results/phase0/live/calls.csv` 逐行独立合计：
- uncached_input_tokens = **27316**
- cache_read_tokens = **29184** (A=16384 B=6400 C=6400 D=0)
- total_prompt_tokens = **56500** (A=21325 B=11725 C=11725 D=11725)
- output_tokens = **3833**
- weighted overall hit rate = **29184 / 56500 = 51.65%**
- estimated offpeak cost = **¥0.0460417392**

但 docs/PHASE0_RESULTS.md 和 executor_report.md 称 prompt 45500，cache_read 22784；status.json overall_cache_read_share 0.5006。与 CSV/summary 按组加总不符。修复时切勿更改真实 CSV 来配合旧数字；由聚合自动生成文档统计与一致性测试。

### R2 — API 调用成功并不等于任务输出成功

100 条记录中 41 条 finish_reason=`max-tokens`（A=0 B=13 C=10 D=18），其余 59 是 completed。缓存 usage 样本可以有效，但 41 条截断不能宣称完整响应，更不代表 JSON 验证成功。CSV 没有响应原文，余下 59 条任务内容有效性也无法独立判断。需要分别报告计量完整的 API response 与任务格式验证状态。

### R3 — 失败和重试请求可能漏记成本

`src/causalevo/benchmark.py::_execute_call` 只有 `outcome.ok` 才调用 `extract_settled_usage`，即便失败 attempt 附带合法 usage 仍被忽略。没有 usage 的失败 `status=error` 后继续执行，并把费用作为 0 纳入 gate。与 P0.4 的 fail-closed、重试计量承诺不一致。应将未知费用分开标记并停止，或保守冻结证明不超限；默认应 STOP。

### R4 — 配置可复现性受损

`src/causalevo/redaction.py::_SENSITIVE_KEY_RE` 中宽泛 `token` 误删配置 `max_tokens`、`prompt_overhead_tokens`，在提交的 live/config_snapshot.json 已看到 `[REDACTED]`。CLI 运行时修改 dataclass `calls_per_group` / `max_cny`，但 `config_hash()` 仅哈希 `config.raw`，因而有效配置的变化可能不改变 hash。需要改并补测试。

### R5 — 余额差值不是已核实账单金额

平台可见余额 4.83→4.83；分辨率/入账延迟不明。当前 status.json 写 actual_billed_cost_cny:0.0，属于过度确定。修为 unknown/null，与 based-on-rate ¥0.0460 估算区别开。

## 三、Gates 评估

| Gate | 状态 | 依据 |
|---|---|---|
| G1 | PASS（有版本证据） | SDK/runtime 锁定与上游 SHA |
| G2 | CONDITIONAL | 42 tests 为 Executor 报告，Planner 未本地重跑；代码/测试可读取 |
| G3 | CONDITIONAL | profile patch + no-tool 证据，仍依赖 Executor runtime 实测 |
| G4 | **FAIL** | error/unknown usage 未可靠计费，配置可复现性受损 |
| G5 | PASS | 四组分配、固定生成器，A 混杂已说明 |
| G6 | PASS for metered observations | 100 条有效计量行；**非** 100 条完整 JSON 响应 |
| G7 | PARTIAL-PASS | GitHub remote HEAD 证实；Executor self-report local clean 未独立验证 |
| G8 | PASS | 没有宣称因果进化/缓存降本的未证实结果 |

总评：Phase 0 实验数据值得保留，修复应完全复用原始 CSV，不重跑收费调用。所有问题限定在安全计费与审计语义的薄层修正。修复后可审查进入 Phase 1。
