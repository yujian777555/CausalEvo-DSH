# Executor Report — CE-DSH-P4-R1.12-REVIEW-FIX5

日期：2026-11-04。Executor：Kimi。正式计划：`planner/latest_plan.md`；当前独立复审：`planner/reviews/CE-DSH-P4-R1_12-review-fix4-independent-review.md`。

**本轮仅离线修复：新增真实 DeepSeek 调用 0 次、新增费用 ¥0；未运行 live pilot/canary，未查询余额，未进入 Phase 5。**

## A. 接管与证据边界

- 实际 `git ls-remote origin main`、fast-forward 后的本地 HEAD 均为 `3ae1913fa87a23eebab8e6ec3ff33a31a8448fe5`，接管时工作区 clean。它包含 Planner 对 FIX4 提交 `717a1fbe8371a444c33f02ff9300c90505ec5ea7` 的复审及 FIX5 元数据，未回退或覆盖这些提交。
- 当前 Planner 决定是 FIX4 `REQUEST_CHANGES`。历史复审和验收记录保持不变；本报告中的测试、哈希、账本和 Git 命令均为 Executor 实际执行结果，不声称 Planner 已独立重跑。
- 未修改 R1.12 原始 `tasks.jsonl`、`events.jsonl`、`proxy-ledger/ledger.jsonl`，未修改 Phase 0–3 或历史 R1.9 冻结数据。

## B. Task A：收窄 symlink skip 分类

- `tests/test_r12_hashes.py::_symlink_unavailable` 是确定性纯分类器：`NotImplementedError`、symlink 创建上下文的 WinError 5/1314，以及 `EPERM/EACCES/ENOTSUP/EOPNOTSUPP/ENOSYS` 返回 True；`EIO/ENOSPC/ENOENT`、普通 OSError 和其他异常返回 False。可选 errno 使用 `getattr`，避免平台缺失。
- containment 测试只对上述明确不可用情况 skip，其他 OSError 原样 `raise`。唯一 `mkdtemp` 目录及 `finally` 清理保留。
- 新增 13 组分类器参数化用例，并用 monkeypatch 使 `Path.symlink_to` 抛出 EIO；测试确认 OSError 传播而非变成 skip，同时确认注入后的临时目录不存在。
- TDD RED 包括分类器未实现的 `NameError`，以及旧实现把 EIO 变成 `Skipped` 的预期失败。修复后完整 `test_r12_hashes.py` 为 **23 passed / 1 skipped**，唯一 skip 为真实 Windows WinError 1314。
- 主执行者实际运行 `wsl -d Ubuntu-22.04 bash -c 'cd /mnt/d/CausalEvo-DSH && python3 scripts/symlink_escape_check.py'`：脚本真实创建链接，内部 verifier 输出 `exit_code: 1` 和 `FAIL: pilot_tasks: path escapes allowed artifact root 'results/phase4/live2/symlink-escape-check-hztqojfm/tasks.jsonl'`，随后输出 `SYMLINK-ESCAPE-REJECTED-CONFIRMED-LINUX`；脚本退出码 0，唯一目录被清理。

## C. Task B：强制 Holm primary 不变量

- `scripts/analyze_r12_replication.py::apply_secondary_holm(primary_key, raw_p_by_key)` 现在接收包含 primary 的完整 raw-p mapping；primary 缺失时抛出明确 `ValueError`。
- 函数内部先排除 primary，再仅对三个 secondary 调用 Holm；primary 输出恒为 `None`，不会被字典展开覆盖。`main()` 传入全部四个比较的 raw-p mapping，不再向 helper 预过滤 primary。
- 集成测试的输入实际包含 primary raw p=`0.001`，断言 primary 为 `None`、三个 secondary 分别调整为 `0.03/0.08/0.20`；把 primary 改为 `0.9` 后 secondary 结果不变。缺失 primary 也有回归测试。
- RED 实证：旧实现将 primary 错调为 `0.004`，测试输出 `1 failed, 3 passed`；修复后 `tests/test_holm_mapping.py` 为 **5 passed**，退出码 0。
- lexical negative-control、ties、累计最大值、单调性和 `[0,1]` 测试全部保留。实验行、raw p 值、统计定义和预注册结论未改。

## D. Task C：clean-clone 强制远端核验

- `scripts/clean_clone_check.py::main()` 无论是否传显式 SHA 都先调用 `_remote_sha()`；远端不可确定返回 3，显式 SHA 与远端不一致在 `mkdtemp`、clone、install 前返回 2。
- 读取实际 `remote.origin.url` 并单分支 clone `main`；clone HEAD 必须等于已经查询的 remote SHA。本地未推送的显式 SHA 因与远端不一致而不能进入 clone。
- clone 子进程使用 `capture_output=True, text=True`，错误路径仅输出固定脱敏消息；不输出 remote URL。成功输出准确写明 `verified origin/main` 和 `configured origin clone`。
- 新增 `tests/test_clean_clone_check.py` 七项离线测试：显式 SHA mismatch、远端未知、实际 origin main clone、成功文案脱敏、关键套件包含本测试、clone 失败脱敏、cloned HEAD mismatch 在安装前停止。最后该项是只读代码复核发现缺口后补强的负例，复核已通过。
- TDD RED 实证包括显式 SHA 路径未查询远端、clone 未捕获子进程输出等预期失败；最终 `tests/test_clean_clone_check.py` 为 **7 passed**，退出码 0。单元测试未真实 clone 或安装；真实完整门禁仅在最终提交后执行。

## E. 专项测试与哈希

实际命令：

`.venv/Scripts/python.exe -m pytest tests/test_r12_hashes.py tests/test_holm_mapping.py tests/test_clean_clone_check.py tests/test_analysis_determinism.py tests/test_frozen_task_set.py -q`

结果：**`46 passed, 1 skipped in 24.61s`**，退出码 0。唯一 skip 为 Windows symlink 权限，不是 passed。随后 `scripts/verify_r12_hashes.py` 输出 **`HASH VERIFIED: 12 artifacts`**，退出码 0。`manifest_reconciled.json` 仅更新 `analysis_script` 的 SHA-256，其他工件引用不变。

## F. 冻结数据、覆盖与账本复核

- canonical task manifest SHA-256：`fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`。实际校验：26 个任务、种子 `20261027/20261028`、4 臂、208 个唯一 `(task_id,seed,arm)`，无缺失或额外键。
- R1.12 原始 SHA-256：tasks `b07c743779bc678ed7723a0bc5bf9af429aca2af3d59a45f43e4a9a1146a6220`；events `ad5a5fda2818498912fc423da8312aaf6e9e3e7a69aecfac13dbc59228129986`；ledger `a8f922ba5695d2258c35c4577f5aeb806c00bca55e428452f41b1bf758e944bb`。
- Phase 0 `calls.csv`：`1961bdd81a7f6a4ad4169d6f246530ed3df3170f70948f85de13ca136e364c59`；历史 312 行投影：`35b9e67a418cfd55fd9e820ab48980750da7ab12d24bc61392768f24b27e4afa`；Phase 3 sweep：`15e2cb844584398d5ce2e65c4ccb1c5bf6be052ab6436cee75815e14e4540ab4`；历史 Monte Carlo：`39a7d7829e28db7629db6881f84561be779ffb9d5ef14b3f9b088c598b578b1c`。Git 差异确认这些冻结范围未改。
- 逐 request_id 终态复核：pilot 714 次 settled、canary 24 次 settled，总计 738；非 settled 终态为 0。按十位小数归一费用为 **¥1.0397171982**，UNKNOWN 上界 ¥0。未通过新请求重建证据。
- FIX4 smoke 工件继续仅为 fake-provider 机制证据，SHA-256 保持 `0e391ac6f44107bb38272928d8fb0ea3093c4ecb375f35f77a0f5574c2304a80` 和 `7582ddd40b327b20462905f8aafec6a95b907a41d0dd0dc71ad7102ba36a6f06`；不表示真实模型 efficacy。

## G. 全量回归与最终门禁

Docker `29.3.1` 已在全量测试前实际确认可用。实际执行 `.venv/Scripts/python.exe -m pytest tests/ -q`，原始摘要为 **`687 passed, 1 skipped in 829.51s (0:13:49)`**，退出码 **0**。唯一 skip 为 Windows symlink WinError 1314，不计为 passed；专项 46/1、全量 687/0/1 与最终 clean-clone 子集分开记录。

最终提交 SHA、远端一致性和 clean-clone 结果以实际终端证据为准；最终 clean-clone 结果在完成回复中提交，不在门禁后追加 tracked-file 修改或提交。

## H. 不变的研究结论与限制

- CEA-v2-online 相对随机或静态 Pareto 基线没有提升证据；主比较差值为 0，精确簇检验 p=1.0，95% CI 跨 0。
- 真实 R1.12 中 NSGA-III 父代选择和幸存者选择调用均为 0；离线代码或测试通过不表示真实在线 NSGA-III 已验证。
- 仅 5 条行为观察，不能证明可靠的已学习干预策略；L4 RSI 尚未实现；本轮是同任务集新种子复制，不是未见任务泛化。
- 代理账本缺少逐请求 Token 桶和定价档位，逐请求 Token 重计价不可复算。Windows symlink 权限仍是明确 skip；Linux 证据来自真实 standalone 校验脚本。
