# Executor Report — Plan CE-DSH-P0-R1 (Phase 0)

日期：2026-10-10。Executor：Kimi。本报告只含已实际运行的结果；无 PASS 虚标。

## 总览

- 全部 Phase 0 工程交付完成；live 基准 100/100 有效调用达成（Gate G6 的 live 路径完成）。
- 测试：42 passed / 0 failed / 0 skipped（`pytest tests/ -q`，真实运行，含失败注入）。
- 实际估算费用：off-peak ¥0.0460（peak 上界 ¥0.0921）；余额对账 4.83→4.83 CNY（低于显示分辨率，已披露）。
- 阻塞项：无未决阻塞。两项如实披露的限制见文末。

## 任务逐项状态

| 任务 | 状态 | 证据 |
|---|---|---|
| P0.1 仓库结构与依赖锁定 | PASS | pyproject.toml、requirements-lock.txt（含 wheel sha256 与上游 SHA d7432673…）、README |
| P0.1 HARNESS_INTEGRATION.md | PASS | docs/HARNESS_INTEGRATION.md（调用链、session 生命周期、usage 事件实测结构、上游 SHA） |
| P0.1 版本兼容核验 | PASS | sdk 0.1.5rc1 + runtime-bin 0.1.5rc1 win_amd64 实测可用；wire model=deepseek-flash（≠ SDK 默认别名 deepseek-v4-flash，按官方价格页二者同模型同价） |
| P0.1 dry-run / fake / live 三模式 | PASS | --dry-run 默认；无 DEEPSEEK_API_KEY 时 live 拒绝（PermissionError 测试） |
| P0.2 工具禁用（非 prompt 级） | PASS | configs/dsh_bench_patch.yml 禁用 50+ 插件；组合 dump 验证；live 100 次调用零工具事件；test_tool_disable.py 回归守卫 |
| P0.2 上传通道关闭 | PASS | session-telemetry-otel（OTLP 默认外发）与 session-log-deepseek 均 disabled |
| P0.2 隔离 workspace / DSH_HOME | PASS | 每次运行独立目录（gitignored）；DSH_PERMISSION_MODE=read-only 纵深防御 |
| P0.2 重试/并发/max_tokens 限制 | PASS | 串行、max_retries=1、maxTokens=64（≤256 上限内） |
| P0.3 四组 25 次基准 | PASS | 100/100 ok；A 0.748 / B 0.546 / C 0.546 / D 0.000；交错顺序记录在 calls.csv |
| P0.3 A 组混杂标注 | PASS | summary.json confounds + PHASE0_RESULTS §3 |
| P0.3 D 组≠in-history update | PASS | 已在配置与结果文档明确声明 |
| P0.4 互斥 token 桶 | PASS | src/causalevo/usage.py；tests/test_usage.py（含分片不求和、多步求和、缺桶 fail-closed） |
| P0.4 价格记录与 CNY 换算 | PASS | 价格页 2026-10-10 快照、峰/谷双价、cache-write 按 miss 上界并披露、FX 假设记录 |
| P0.4 预算门控 fail-closed | PASS | BudgetGate 预检+逐次门控；余额 4.83 < 授权 10 → 有效上限自动收紧；超支拒绝测试 |
| P0.4 账单对账 | PARTIAL | /user/balance 前后各查一次，delta=0.00（消费低于 0.01 CNY 显示分辨率或账单延迟）；以价格表估算为准并披露 |
| P0.5 交付件清单 | PASS | benchmarks/cache_benchmark.py、configs/、src/causalevo/、tests/、docs/、results/phase0/ |
| P0.6 Gates | 见下 | Executor 不自行判定 ACCEPTED |

## Gate 自评（供 Planner 核验）

- G1 PASS：锁定版本+哈希+上游 SHA（requirements-lock.txt、HARNESS_INTEGRATION.md）。
- G2 PASS：离线 dry-run + 42 测试（含失败注入：缺 usage 停机、预算拒绝、重试计量）。
- G3 PASS：工具禁用为 profile patch 机制级；冒烟+正式 run 无任何工具事件；workspace/DSH_HOME 隔离。
- G4 PASS：Key 仅 env、不落盘；产物脱敏测试通过；桶与上游类型一致；fail-closed 实现并被测试触发验证。
- G5 PASS：四组固定生成器 + 长度不变量测试；A 组混杂标注。
- G6 PASS（live 完成）：100/100 有效调用，逐次证据 results/phase0/live/calls.csv。
- G7 待提交后核验：远端 SHA 一致性将在 push 后于本报告补记。
- G8 PASS：未声称缓存降本结论或进化效果；结果仅为测量值+混杂披露。

## 运行记录

- 测试命令：`.venv/Scripts/python.exe -m pytest tests/ -q` → 42 passed。
- 离线基准：`--dry-run --run-id dryrun002` → 100/100 fake ok。
- live 冒烟：1 次（scripts/smoke_live.py，验证 wire id/usage 结构/无工具）。
- live 正式：`--live --run-id p0live02` → 100/100 ok，0 重试，约 70 秒，全程 off-peak。
- Token 总量：prompt 45,500（cache_read 22,784）；output 3,833。整体 cache_read 占比 50.1%。
- 费用：估算 off-peak ¥0.0460 / peak 上界 ¥0.0921；另有开发期 2 次表外调用 ≈ ¥0.001。
- 失败与缺陷：首次 live 运行（p0live01）因 pricing 对未上报 cacheWriteTokens(None) 未做兜底而崩溃（1 次调用后）——已修复（pricing.py）并补回归测试 test_unreported_cache_write_bills_as_zero；修复后 42 测试全绿再重跑正式基准。此为已修复缺陷的如实记录。

## 限制与披露

1. 平台余额对账分辨率不足（0.01 CNY），实际扣费差值显示为 0；成本以官方价格表估算，peak 口径为上界。
2. 上游不上报 cacheWriteTokens：该桶按缺失披露，命中率为 cache_read/(uncached+cache_read)。
3. 100 次调用集中于约 70 秒窗口（已交错分组）；缓存粒度 128 tokens 为观察推断。
4. 本阶段不构成任何因果进化或缓存降本效果的结论。

## 下一轮建议（供 Planner）

- 若需更高命中分辨率，可加长公共前缀至 ≥1k tokens 并观察 128-token 粒度边界。
- 如需验证 in-history system-prompt-update，需要单独的机制实验设计。
