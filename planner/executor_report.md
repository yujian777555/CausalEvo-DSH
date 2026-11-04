# Executor Report — CE-DSH-P4-R1.12-REVIEW-FIX4

日期：2026-11-04。Executor：Kimi。正式计划：`planner/latest_plan.md`；当前独立复审：`planner/reviews/CE-DSH-P4-R1_12-review-fix3-independent-review.md`。

**本轮仅离线修复：新增真实 DeepSeek 调用 0 次、新增费用 ¥0；未运行 live pilot/canary，未查询余额，未进入 Phase 5。**

## A. 接管与范围

- 实际同步后的 `origin/main` / 本地接管 SHA：`5d1c12c3d9b709530e6decbaa4bd7289826b2b97`。它晚于 Planner 复审基线 `ddbb1f82498c4e7bce4d52eed591e32811e3399b`；新增提交为 FIX4 计划、复审状态及 handoff 更新，未覆盖或回退这些提交。
- 保留 FIX1/FIX2/FIX3 的历史结论；本报告只把 FIX3 的 `REQUEST_CHANGES` 作为当前待关闭复审项。历史 clean-clone PASS 仅属于 `b9c949981c8489ada1a48a8cad43a57a3895115c`，不能覆盖当前分支。
- 未修改 R1.12 原始 `tasks.jsonl`、`events.jsonl`、`proxy-ledger/ledger.jsonl`，未修改 Phase 0–3 或历史 R1.9 冻结数据。

## B. Task A：symlink 清理与可独立复现的 Linux/WSL 校验

- `tests/test_r12_hashes.py::test_symlink_escape_rejected_if_supported`：在允许的 `results/phase4/live2/` 下使用 `tempfile.mkdtemp` 创建唯一目录；目录/链接创建、验证与平台 skip 均受 `try/finally` 清理保护。链接指向根外的 `status.json`，实际调用 `scripts/verify_r12_hashes.py`，断言退出码 1 且包含 `escapes allowed artifact root`。
- `scripts/symlink_escape_check.py`：改为自包含脚本，独立创建唯一 symlink 与临时 manifest，调用同一验证器，检查拒绝并在 `finally` 删除整个唯一临时目录。可从仓库外的工作目录运行，不依赖其他测试遗留文件。
- 删除无独立用途且重复的根目录 `tmp-symlink-check.py`。
- Windows 实际命令：`.venv/Scripts/python.exe -m pytest tests/test_r12_hashes.py::test_symlink_escape_rejected_if_supported -q -rs`。结果：`1 skipped in 0.24s`，退出码 0；原因是 `[WinError 1314]` 当前账户没有创建 symlink 的权限。该用例没有计为 passed，临时目录已清理。
- WSL/Ubuntu-22.04 实际命令：`wsl -d Ubuntu-22.04 bash -c 'cd /mnt/d/CausalEvo-DSH && python3 scripts/symlink_escape_check.py && python3 scripts/symlink_escape_check.py'`。两次均创建不同的随机目录，内部验证器均输出 `exit_code: 1` 与 `FAIL: pilot_tasks: path escapes allowed artifact root`，随后输出 `SYMLINK-ESCAPE-REJECTED-CONFIRMED-LINUX`；整条命令退出码 0。第三次在最终测试代码上再次得到同一拒绝结果。
- 额外尝试 `wsl -d Ubuntu-22.04 ... python3 -m pytest ...` 未执行到测试：WSL Python 报 `No module named pytest`，退出码 1。未把它冒充测试通过；Linux 证据来自上述真实自包含校验脚本。

## C. Task B：Holm 负对照与生产逻辑集成

- `tests/test_holm_mapping.py` 的负对照使用 `comparison_z=0.01, comparison_a=0.20, comparison_m=0.04`：raw-p 键序 `[z,m,a]` 与字典键序 `[a,m,z]` 被显式断言为不同。正确调整为 `z=0.03, m=0.08, a=0.20`；测试显式证明按字典键错配会将 `a` 错赋为 `0.03`，而非正确的 `0.20`。
- 保留并执行 distinct-p、ties、累计最大值、单调性和 `[0,1]` 边界检查。额外故障注入把 helper 临时替换成旧字典序映射，实际观察负对照以 `AssertionError` 失败；随后恢复 helper，未修改生产文件来制造失败。
- 新增生产纯函数 `scripts/analyze_r12_replication.py::apply_secondary_holm(primary_key, secondary_raw_p)`：主比较固定返回 `None`，仅三个次要比较经 `holm_adjusted_by_key`。`main()` 实际调用该函数。集成测试直接调用生产函数，不再只读取提交的 `analysis.json`。
- 实际命令 `.venv/Scripts/python.exe -m pytest tests/test_holm_mapping.py -q`：`4 passed in 0.43s`，退出码 0。主比较 `CEA-v2-online vs B1-random` 未校正，三个预注册次要比较全部校正。
- 原始 p 值、208 行实验记录、统计定义与预注册结论未改。

## D. Task C：smoke 工件溯源与范围

保留以下两个既有工件：

- `results/phase4/cea_v2_agent_smoke/run-20261028T125616Z/manifest.json`，SHA-256 `0e391ac6f44107bb38272928d8fb0ea3093c4ecb375f35f77a0f5574c2304a80`。
- `results/phase4/cea_v2_agent_smoke/run-20261028T125616Z/controller_state.json`，SHA-256 `7582ddd40b327b20462905f8aafec6a95b907a41d0dd0dc71ad7102ba36a6f06`。

生成路径为 `python scripts/run_phase4_r19_pilot.py --offline-smoke`，对应 `offline_smoke()`；manifest 的 `provenance_block()` 记录源 revision `c007b5c64280bad53c5c6f272be961eca472e855`、UTC 时间及固定运行环境。其用途是 fake-provider + Docker 的 adapter integration mechanism smoke，验证选择、干预、Judge/账本反馈和控制器状态接线，不是模型效果证据。

`tests/test_cea_v2_integration.py` 会自行运行 `--offline-smoke` 并解析新工件；仓库中该固定 run ID 没有测试引用，因此这两个文件不是测试的固定输入。保留它们仅作为该次机制 smoke 的可审计样本。逐字段读取及敏感模式扫描均未发现凭据、API Key、raw provider 请求体、prompt 或 session log；不得把它们表述为真实模型 efficacy。

## E. 冻结数据、任务覆盖与账本复核

- `scripts/verify_r12_hashes.py` 实际输出：`HASH VERIFIED: 12 artifacts`，退出码 0。精确 12-label inventory 由验证器强制；`manifest_reconciled.json` 仅因生产分析脚本 SHA 变化而更新对应 `analysis_script` 项，原始 tasks/events/ledger 哈希不变。
- canonical task manifest：`fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`。实际校验为 26 个任务、种子 `20261027`/`20261028`、4 个实验臂、208 个唯一 `(task_id,seed,arm)`，无缺失或额外键。
- 原始 R1.12 SHA-256：tasks `b07c743779bc678ed7723a0bc5bf9af429aca2af3d59a45f43e4a9a1146a6220`；events `ad5a5fda2818498912fc423da8312aaf6e9e3e7a69aecfac13dbc59228129986`；ledger `a8f922ba5695d2258c35c4577f5aeb806c00bca55e428452f41b1bf758e944bb`。
- Phase 0 `calls.csv`：`1961bdd81a7f6a4ad4169d6f246530ed3df3170f70948f85de13ca136e364c59`；历史 312 行投影 `auditable_tasks.jsonl`：`35b9e67a418cfd55fd9e820ab48980750da7ab12d24bc61392768f24b27e4afa`；Phase 3 sweep：`15e2cb844584398d5ce2e65c4ccb1c5bf6be052ab6436cee75815e14e4540ab4`；历史 Monte Carlo：`39a7d7829e28db7629db6881f84561be779ffb9d5ef14b3f9b088c598b578b1c`。Git 差异确认这些冻结范围未被修改。
- 逐 request_id 终态复核：pilot 714 次 settled、canary 24 次 settled，总计 738；非 settled 终态为 0。原样浮点十进制展开为 `1.0397171981999999155`，按已报告十位小数口径归一为 **¥1.0397171982**；既有 `_round_spend` 浮点结果为 `1.0397171981999986`，归一到十位小数相同，UNKNOWN 上界 ¥0。未通过任何新请求重建证据。

## F. 实际测试记录

- symlink Windows 专项：`1 skipped`，权限原因如上；WSL 独立脚本通过，重复运行无遗留目录。
- Holm 专项：`4 passed / 0 failed / 0 skipped`，退出码 0。
- 最终 FIX4 专项命令 `.venv/Scripts/python.exe -m pytest tests/test_r12_hashes.py tests/test_holm_mapping.py tests/test_analysis_determinism.py tests/test_frozen_task_set.py -q`：**`24 passed, 1 skipped in 9.31s`**，退出码 0；随后哈希验证再次输出 `HASH VERIFIED: 12 artifacts`。
- 账本/历史估计/R1.12 分析及预算四套件联合：`116 passed in 104.90s`，退出码 0。
- Docker 不可用时的第一轮全量：`608 passed, 58 skipped in 243.27s`，退出码 0；`docker info` 明确报 `dockerDesktopLinuxEngine` pipe 不存在。该轮不作为最终 Docker 覆盖证据。
- 启动既有 Docker Desktop 后，`docker info --format '{{.ServerVersion}}'` 返回 `29.3.1`。随后对最终代码重新执行 `.venv/Scripts/python.exe -m pytest tests/ -q`，原始摘要为 **`665 passed, 1 skipped in 724.87s (0:12:04)`**，退出码 **0**；唯一 skip 为已披露的 Windows symlink 权限限制。该轮与 Docker 不可用时的 608/58 第一轮严格分开记录。
- Planner 未独立重跑这些测试；所有本轮运行数字均为 Executor 终端结果。最终 clean-clone 的关键套件子集计数将与全量 665/0/1 分开报告。

## G. Git 与最终精确 SHA 门禁

最终提交 SHA、远端一致性和 clean-clone 结果将在实际提交、推送和门禁执行后通过完成回复提交给 Planner。仓库内不预写未来 SHA，不声称当前 HEAD 已通过尚未执行的 clean-clone。最终门禁通过后不追加文档或其他提交。

## H. 不变的研究结论与剩余限制

- CEA-v2-online 相对随机或静态 Pareto 基线没有提升证据；主比较差值为 0，精确簇检验 p=1.0，95% CI 跨 0。
- 真实 R1.12 中 NSGA-III 父代选择和幸存者选择调用均为 0；不得把离线实现或测试通过称为真实在线 NSGA-III 已验证。
- 仅 5 条行为观察，不能证明可靠的已学习干预策略；L4 RSI 尚未实现；本轮为同任务集新种子复制，不是未见任务泛化。
- 代理账本缺少逐请求 Token 桶和定价档位，逐请求 Token 重计价不可复算。
- Windows symlink 权限限制仍为平台 skip；WSL 缺少 pytest 已单独披露，独立脚本证据与 pytest 结果未混算。
