# CE-DSH-P4-R1.9 — 证据对账报告（Reconciliation）

日期：2026-10-26。依据：原始本地文件（未修改）与脱敏投影 `results/phase4/r19-audit/`。所有数字均由 `scripts/build_r19_audit.py` 从原始账本重算，非手工编造。

## 1. 原始文件与哈希（可独立复核）

| 文件 | SHA-256 |
|---|---|
| `results/phase4/live2/phase4-r19-pilot-20261024T151323Z/tasks.jsonl` | `ae051b2195d6655eacdd4ab3b1e11636a072dac1dd4bb2d8a72a74f9e87dcb29` |
| `…/events.jsonl` | `9fab748b58e193a759f4d47a9dbdada3bd4121108b9e1388fe0a8080bd5104c3` |
| `…/proxy-ledger/ledger.jsonl` | `0de752b789fea31af52f12c0d542809f7e0a7b37e5ec17275f4a97fe96f30a34` |
| `…/manifest.json`（原始，保留不改） | `c941c40b63c6611295f1bd51c2d7956611dff2fa2adc807862fd0fcfef65953f` |

投影：`results/phase4/r19-audit/{auditable_tasks,auditable_events,auditable_ledger}.jsonl` 与 `manifest_reconciled.json`（含源文件与投影哈希、字段定义）。

## 2. 行数与请求数（逐 request_id 对账）

### 2.1 208 行任务记录

- `auditable_tasks.jsonl`：208 行 = 26 任务 × 2 种子 × 4 臂；`(task_id, seed, arm)` 键唯一，覆盖完整。
- `manifest.json` 的 `rows=58` 只是**最后一个续跑进程**新执行的行数；正确语义为 `rows_written_last_process=58`。**`rows_total=208`**（由 `analysis.json` 与投影一致确认）。原始 manifest 字节保留（哈希见上），`manifest_reconciled.json` 以明确字段修正。

### 2.2 总 SETTLED 请求数 = 912（唯一 request_id 终态为 SETTLED）

| 来源 run | SETTLED 请求数 | settled 费用（CNY，peak） |
|---|---|---|
| canary（成功） | 24 | 0.029164 |
| canary（unknown_cost 中止） | 2 | 0.005578 |
| run1（权限错误中止） | 13 | 0.015335 |
| run2（livelock 停止） | 180 | 0.261382 |
| final_resumed（正式 pilot 及续跑） | 693 | 0.994880 |
| **合计** | **912** | **1.306339** |

UNKNOWN：1 次（`fe088dd586454e9296aef973143a258a`，SSE IncompleteRead），预留上界 **0.157041 CNY**，不计入 SETTLED 费用、不重复计数。

### 2.3 行级 provider_calls = 699 与 693 的差额 = 6

逐 scope 对账结果：**207/208 行**的 `provider_calls` 与该 scope 的 proxy SETTLED 数完全一致；唯一不一致行为 `micro-011-second_largest / B1-random / 20261014`（IncompleteRead 中止行）：

- 该行 `provider_calls = 6`，proxy 对该 scope SETTLED = 0。
- 该 scope 账本序列：`1 RESERVED + 1 SENT + 1 UNKNOWN + 5 REJECTED`。

因此：

```
699（行级尝试） = 693（proxy SETTLED） + 1 UNKNOWN + 5 REJECTED = 699
```

即 6 个差额**全部**来自该中止行的 1 个未知费用请求 + 5 个 gate-stopped 拒绝请求；这些尝试在行级事件中被记录，但在 proxy 端没有 SETTLED。**不存在无法解释的请求，也不存在重复计费**。

### 2.4 正式 pilot 693 与"正式实验请求"的口径

`final_resumed` 的 693 = 正式 pilot（含续跑）proxy SETTLED 请求；912 = 693 + 24 + 2 + 13 + 180（canary 与中断 run）。此前报告按此分解，现经逐 request_id 复核一致。

## 3. 费用与上限

```
round_total = 1.306339（SETTLED，peak） + 0.157041（UNKNOWN 上界）
            = 1.463380 CNY  <  2.00 CNY 硬上限
```

- 每 run 的 `proxy-ledger/ledger.jsonl` 独立完整；中断 run 费用全部计入，无账本重置。
- 最终 run 的 `proxy_final.settled_cost_cny=0.9948804852` 仅对应该 run（693 请求），而 `1.306339` 为全轮多 run 合计——两者口径不同，现已明确。

## 4. 未知费用处理

- UNKNOWN 请求的成本未知，以 worst-case 预留上界 0.157041 计入总成本保守值；未加入 SETTLED 费用、未清零、未自动改写原账本。
- 续跑时按 scope 人工对账（`manual_reconcile`，scope=None + scopes + reason），保留审计事件。

## 5. 不能恢复的部分

无。原始 `tasks.jsonl`、`events.jsonl`、`proxy-ledger/ledger.jsonl` 均在本机存在并已投影（含哈希）。无需标记 NOT_REPRODUCIBLE。

## 6. 账本数据边界（不伪造字段）

- **可独立复算**：SETTLED 状态迁移的 `cost_cny` 求和 + UNKNOWN 预留上界（本轮 = 1.3063390536 + 0.15704064 = 1.4633796936 CNY）。
- **行级聚合 token 桶**：`auditable_tasks.jsonl` 每行含 `input_tokens`、`cache_read_tokens`、`output_tokens` 聚合值，可用于行级成本/缓存分析。
- **不可独立复算**：源 proxy 账本**不持久化逐请求 token 桶与定价档位**，因此**逐请求 token 级重计价不可独立复现**。上述行级聚合 token 无法一一映射回每个 proxy 请求。不得伪造这些字段。
- `auditable_ledger.jsonl` 的 `seq` 字段仅保留各 run 内源文件顺序，**不表示 token 信息**。
- `intervention_text` 为**有意保留**（动作级审计）；准确口径为：排除原始请求/响应体、完整 provider payload、凭据与原始会话日志，而非"不含任何 prompt"。

## 7. 敏感性分析（事后，非预注册主检验）

`results/phase4/r19-audit/sensitivity.json` 由 `scripts/analyze_r19_cluster_sensitivity.py` 以**精确动态规划**生成（26 簇、两种子同簇、2^26 符号分配全枚举），精确双侧 p：

| 比较 | 精确 p |
|---|---|
| CEA-v2 vs B1-random | **0.750000** |
| CEA-v2 vs B5-v1-frozen-pareto | **0.625000** |
| CEA-v2 vs B0-original | **0.7265625** |
| B5-v1-frozen-pareto vs B1-random | 1.000000 |

此前的 20000 次置换估计（0.7462 / 0.62095 / 0.7268）保留在 `previous_monte_carlo_estimates` 字段，未被覆盖。脚本与结果 SHA-256 已写入 `manifest_reconciled.json` 的 `sensitivity_artifacts`。

