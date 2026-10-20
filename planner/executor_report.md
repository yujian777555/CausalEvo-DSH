# Executor Report — CE-DSH-P4-R1.2（Clean-Clone 可复算 + Provider Proxy 接入）

日期：2026-10-20。Executor：Kimi。本轮**新增真实 API 调用 0 次、费用 ¥0**。历史冻结数据（Phase 0–3、Phase 4 312 行）未修改。

## Gate 结果

| Gate | 状态 | 证据 |
|---|---|---|
| A 干净克隆可复算 | PASS | scripts/clean_clone_check.py 实测：fresh git clone + 新 venv + lockfile 安装 → reconcile 验证 312 行 + 34 项子集测试通过（输出：CLEAN CLONE OK） |
| B Proxy 接入真实运行路径 | PASS | ProxyContainer（双 NIC：ceval-net 内部 + bridge 出口）；run_phase4_pilot.py live 分支实际创建并持有 proxy；harness_agent live 无 endpoint 即 PermissionError；tests/test_proxy_integration_e2e.py 3 项容器 E2E（完整链 judge 通过、cap 中途拒绝且上游只见到 1 次转发、无 proxy 拒绝运行） |
| C 并发/异常/预留 fail-closed | PASS | RESERVED→SENT→SETTLED/UNKNOWN/REJECTED 原子状态机；发送前持久化预留；并发不同 body 全局额度不超（4 线程对撞）；崩溃恢复默认 UNKNOWN 并锁定，人工 reconcile 解锁；可信鉴权注入 + agent 伪造 Authorization 不到上游；tests/test_budget_proxy.py 12 项 |
| D 算法适配器接入新调度 | PASS | scripts/run_phase4_v2_offline.py（experiment_version=p4-r1.2-v2）：B4-v2 经 CausalPolicyAdapter.cea_v0 真实调用 LinUCB controller（snapshot sha256 记录、冻结不更新）；B5-v2 经 cea_v1 加载冻结 Pareto 前沿（genome id + 文件 SHA 校验、失败条件化基因组选择规则冻结并记录选择理由）；旧 312 行不动 |
| E 测试可信 | PASS | 分档：unit（auditable/budget_proxy/adapter 等）+ integration + Docker E2E + clean-clone + 并发预算 + fail-closed + frozen 完整性；全量 447 passed / 0 failed / 0 skipped（Docker 真实参与） |
| F 零新调用 | PASS | 本轮 DeepSeek 调用 0 次、¥0；历史不变 |

## 测试分类明细（S7 要求）

| 类别 | 命令 | 结果 | Docker |
|---|---|---|---|
| Unit+integration（全量） | `pytest tests/ -q` | 447 passed / 0 / 0 | 部分真实参与 |
| Proxy 并发/崩溃/鉴权 | `pytest tests/test_budget_proxy.py -q` | 12 passed | 无（宿主 fake 上游） |
| Docker E2E（agent→proxy→fake→judge） | `pytest tests/test_proxy_integration_e2e.py -q` | 3 passed | 是 |
| Clean-clone | `python scripts/clean_clone_check.py` | CLEAN CLONE OK（34 子集 + reconcile） | 无 |
| Frozen 完整性 | test_live_csv_consistency 等 | 通过 | — |

## 直连配置状态

配置层直连全部落地（空 ProxyHandler + 容器 scrub + NO_PROXY 钉住 + placeholder key 入 agent 容器）；`or True` 永真断言已删，替换为行为断言（无 endpoint 的 live runner 拒绝 + placeholder 校验）。TUN 级仍为 `DIRECT_ROUTE_UNVERIFIED`（需代理客户端日志/规则确认，本轮无 live 调用故无法实测）。

## 尚未解决的风险

1. TUN 路由未证（DIRECT_ROUTE_UNVERIFIED）。
2. Proxy 并发测试规模有限（4 线程）；更高并发需压测。
3. B5-v2 基因组选择规则已冻结并记录；其真实 live 效果需新预算授权的 pilot。

## 停止

停在 Phase 4 R1.2。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。未进入 Phase 5。
