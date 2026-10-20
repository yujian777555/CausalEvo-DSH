# Executor Report — CE-DSH-P4-R1.3（Proxy 凭据隔离 / 账本恢复 / 运行归属 / 请求上限）

日期：2026-10-20。Executor：Kimi。本轮**新增真实 DeepSeek 模型 API 调用 0 次、费用 ¥0**；未运行 `--live`；未做真实余额查询。历史冻结数据（Phase 0–3、Phase 4 2026-10-14 共 312 行）零修改。

计划：planner/latest_plan.md（CE-DSH-P4-R1.3）；审查：planner/reviews/CE-DSH-P4-R1_2-independent-review.md。详细证据文档：docs/PHASE4_R1_3_REMEDIATION.md。

## Gate 结果（计划第九节 A–I）

| Gate | 状态 | 证据 |
|---|---|---|
| A Agent 请求不含真实 API key | PASS | 结构性修复：live 构造必须显式 endpoint+placeholder（否则 ValueError）；run_task 在 proxied 模式忽略调用方 api_key 参数；run_phase4_pilot 不再 set_api_key(真实 key)。canary 测试经真实请求路径（捕获 subprocess stdin/cmd/outcome 序列化）：真实 key 0 次出现（tests/test_secret_isolation.py 7/7） |
| B 重启后 known spend 与 per-scope 计数完整恢复 | PASS | budget_proxy v3 全量重放：状态转换校验、SETTLED 累计、scope 计数、RESERVED/SENT→UNKNOWN、损坏 fail-closed、scoped reconcile 不清历史、fsync。结算 3 次→重启→计数恢复→超限请求 429 且上游计数 0 增长（tests/test_budget_proxy.py 27/27） |
| C 相同 task 重复设置不 ACK 超时；不同 arm/seed 预算独立 | PASS | proxy_control.py：先删旧 ACK→原子发布→回显同一 generation；超时/更新 generation/挂载缺失即拒绝启动 Agent。连续相同 scope×3 不死锁（单元 8/8 + 容器 E2E 回归）；scope=run/task/seed/arm 计数独立 |
| D 未认证 bridge sibling 无法使用 Proxy | PASS | per-run ingress token（≠上游 key，proxy 无 token 拒绝启动）；bridge sibling 容器实测 POST→401，上游 request_count==0，ledger 有 ingress_auth 审计（test_proxy_integration_e2e.py 6/6） |
| E 请求 model/body/token 超限发送前拒绝 | PASS | 路径/方法/Content-Length/JSON 形状/model=deepseek-flash/max_tokens 全部转发前校验；违规不消耗预算；fake 上游 call_count==0 证明（4 项新测试） |
| F Fake Provider 端到端实际计数验证 cap-before-send | PASS | tape_server 每 POST 写 /tape/requests.jsonl；ProviderContainer.request_count()；cap=1 E2E 断言上游恰收 1 次（不再用 proxy SENT 行替代） |
| G CEA-v0/v1 多离线分支真实驱动；SHA 独立 manifest 钉住 | PASS | configs/phase3_artifact_manifest.json 钉住 pareto_front.json(20fdb512…)+sweep(15e2cb84…)；adapter 加载前比对、失配/缺失即 ValueError、每次读前复检；v2 driver 4 场景×2 臂真实容器驱动，3 个行为分支选中**不同** genome，infra(unknown_cost) 双臂不重试（tests 19/19 + 7/7） |
| H clean clone/历史复算一致；冻结数据不变 | PASS | clean_clone_check.py 现校验克隆 HEAD==`git ls-remote origin main`（失配 exit 2，不可达 exit 3 REMOTE_UNVERIFIED）；push 后实测（见末节）。冻结数据 git 校验无差异 |
| I 本轮新增真实模型调用 0、费用 ¥0 | PASS | 全部测试为 fake provider/离线；live 授权 env 未设置 |

## P0 修复明细（对应审查 P0-A…F）

1. **P0-A 密钥隔离**：`harness_agent.py` live 构造强制 placeholder；proxied 请求只用构造期 token；`run_phase4_pilot.py` 真实 key 仅用于宿主余额查询 + `ProxyContainer(upstream_api_key=…)`；`make_live_runner` 工厂。测试：canary 经 stdin JSON/docker cmd/异常 blob 0 泄漏 + 源码守卫。
2. **P0-B 账本恢复**：见 Gate B。另覆盖：幂等重复、冲突重复、负费用、非法 JSON、非法转换、旧 `task_id` 键兼容、reconcile 留痕且不清零。
3. **P0-C ACK 竞态 + P0-D scope 混淆**：见 Gate C。控制消息含单调 generation；宿主串行锁；proxy 只应用严格更新 generation。
4. **P0-E ingress 认证**：见 Gate D。`ProxyConfig` 上游白名单 + https 强制（http 仅宿主可信 fake）。
5. **P0-F 请求上限**：见 Gate E。容器默认 worst-case 65536 prompt / 2048 output tokens（env 可调，宿主可信）。

## P1 补齐

- `--out` 未初始化即读：`_resolve_paths` 前置；subprocess 回归测试（无 NameError， PermissionError 明确）。
- E2E cap 断言改上游真实计数（Gate F）。
- Pareto 独立 manifest 钉住（Gate G）。
- v2 driver 多场景（Gate G）；结果标 `evidence_class=adapter_integration_smoke`，不宣称泛化/真实提升/NSGA-III 优越性。
- clean-clone 远端 SHA 校验（Gate H）。
- status.json 清理旧 blockers，保留历史审查记录。

## 测试分类明细

| 类别 | 命令 | 结果 | Docker |
|---|---|---|---|
| 全量 unit+integration | `pytest tests/ -q` | **496 passed / 0 failed / 0 skipped** | 部分真实参与 |
| 预算/账本/上限/ingress | `pytest tests/test_budget_proxy.py -q` | 27 passed | 否 |
| 密钥隔离 canary | `pytest tests/test_secret_isolation.py -q` | 7 passed | 否 |
| 控制通道协议 | `pytest tests/test_proxy_control.py -q` | 8 passed | 否 |
| Docker E2E（agent→proxy→fake→judge + sibling） | `pytest tests/test_proxy_integration_e2e.py -q` | 6 passed | 是 |
| 算法适配器 | `pytest tests/test_causal_policy_adapter.py -q` | 19 passed | 否 |
| v2 离线驱动 | `pytest tests/test_phase4_v2_offline.py -q` | 7 passed | 是 |
| clean-clone | `python scripts/clean_clone_check.py` | push 后实测，结果见 git 备注 | 否 |
| 冻结完整性 | test_live_csv_consistency / test_phase4_integrity / test_auditable 等 | 通过 | — |

无任何 skip 冒充 PASS；Docker daemon 与两镜像全程可用。

## v2 离线驱动结果（adapter_integration_smoke，非算法效果证据）

run_dir：results/phase4/v2-offline/run-20261020T090554Z（8 行：4 场景 × B4-v2/B5-v2）

| scenario | failure_state（计算所得） | B5-v2 选中 genome | B4-v2 |
|---|---|---|---|
| edited_failing | edited=T, invalid=F, kind=none | e3738653ca40（tool-validation） | knowledge_failure→lib:verification_failure（重试成功） |
| invalid_syntax | edited=T, invalid=T | ef0925c8870c（verification-heavy） | verification_failure→lib:verification_failure |
| no_edit | edited=F | e015506f37fe（read-first） | knowledge_failure→lib:verification_failure |
| infra_unknown_cost | kind=unknown_cost | None（不重试） | lib:execution_failure→None（不重试） |

诚实备注（实施中实测发现并已写入代码注释）：(1) 纯 `no_usage` tape 不产生 unmetered attempt（runtime 记 assistant/message 而非 assistant/attempt），infra tape 因此前置一次 500 重试以真实触发 unknown_cost；(2) 原建议的"错误修复"恰等于原始 buggy 文件，已改为 valid-but-wrong 的 `min(max(x, lo), lo)` 保证 digest 变化真实可测。

## DeepSeek Direct Connection Audit

配置层直连维持：proxy 上游空 ProxyHandler（tests/test_direct_connect.py 5/5）、容器 scrub_proxy_env、NO_PROXY 钉住、agent 仅持 placeholder token。Windows 全局代理为规则模式；TUN/透明代理未启用证据未取——TUN 级保持 **DIRECT_ROUTE_UNVERIFIED**（本轮 0 live 调用，无法实测；直连域名规则需未来 live 授权时经代理客户端日志确认）。

## 尚未解决的风险

1. TUN 级路由未证（DIRECT_ROUTE_UNVERIFIED）。
2. Proxy 并发测试规模有限（4 线程对撞 + 串行归属锁）；更高并发压测未做。
3. v2 结果为 fake-provider 适配器 smoke；CEA-v0/v1 真实模型效果需独立预注册与新预算授权（不属本轮）。
4. LinUCB 在冻结 sweep 上对所有行为 failure_type 选 lib:verification_failure（训练数据仅 3 类），已在每条记录中透明标注 reason/candidates。

## Git 交付（已核验）

- **Commit SHA：1ae933a48623da26d6941e051da4157fa25bd3e7**（本报告与 status.json 的 SHA 记录为随后的 housekeeping commit）。
- `git ls-remote origin main` == 本地 HEAD（push 后实测一致）；工作区 clean。
- clean-clone 实测（push 后）：`CLEAN CLONE OK: HEAD 1ae933a48623 == origin/main; 312 auditable rows recompute in a fresh clone`（fresh clone + fresh venv + lockfile；reconcile 校验 312 行 + 34 项子集测试通过；raw tasks.jsonl 不存在断言保持）。
- 冻结校验：staged diff 中 results/phase0–3 与 results/phase4/live 零改动；密钥扫描 0 命中。
- 23 files changed, 1965 insertions(+), 358 deletions(-)（13 modified + 10 new，含 .gitignore 白名单）。

## 停止

停在 Phase 4 R1.3。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。未进入付费 pilot，未进入 Phase 5。
