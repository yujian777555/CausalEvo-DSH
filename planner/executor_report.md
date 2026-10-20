# Executor Report — CE-DSH-P4-R1.4（严格输出上限 / 按 scope 对账 / 可复现密钥隔离）

日期：2026-10-20。Executor：Kimi。本轮**新增真实 DeepSeek 模型 API 调用 0 次、费用 ¥0**；未运行 `--live`、未查询真实余额、未使用真实密钥发请求。历史冻结数据（Phase 0–3、Phase 4 2026-10-14 共 312 行）零修改。

计划：planner/latest_plan.md（CE-DSH-P4-R1.4）；审查：planner/reviews/CE-DSH-P4-R1_3-independent-review.md。证据文档：docs/PHASE4_R1_4_REMEDIATION.md。

## 基线与最终 SHA

- 基线（Planner）：`9b1abcb18cdbe13700315a9ff101f5f8e41515ee`
- 最终 SHA 与 clean-clone 复验：见末节「Git 交付」（P1-F 要求提交推送后对最终精确 SHA 实测）。

## 变更文件及原因

| 文件 | 变更 | 对应 |
|---|---|---|
| src/causalevo/eval/budget_proxy.py | `_output_limit_problem`/`_validate_output_limit` 严格校验；`_request_scope` 映射；`reconcile(scope)` 按 scope 清除 + `reconcile_requests(ids, reason)` 跨 scope；replay 校验 reconcile 事件与重复事件语义一致性 | P0-A/P0-B/P1-E |
| src/causalevo/eval/networks.py | `_docker(extra_env=...)`；`CE_PROXY_KEY` 改裸 `-e` 透传（argv 无值） | P1-D |
| tests/test_budget_proxy_r14.py | 新增 25 项回归（缺陷复现先行：修复前 21 failed） | P0-A/P0-B/P1-E |
| tests/test_budget_proxy.py | 适配新语义（默认 body 带 max_tokens、reconcile 带本 scope、审计断言） | 配套 |
| tests/test_credential_isolation.py | 新增 9 项（改名自被 `.gitignore *secret*` 吞没的 test_secret_isolation.py；扩展异常/启动失败/argv canary） | P0-C/P1-D |
| tests/test_proxy_integration_e2e.py | 新增 key 环境送达/argv 洁净容器测试（7 项总） | P1-D |
| scripts/clean_clone_check.py | clone 内增跑 7 个关键套件 | P1-F |
| docs/PHASE4_R1_4_REMEDIATION.md | 本轮证据文档 | — |
| docs/PHASE4_R1_3_REMEDIATION.md | 更正失实测试路径（保留历史，加注更正） | P0-C |
| status.json / planner/executor_report.md | R1.4 状态与报告 | — |

## P0-A：输出 token 上限严格 fail-closed（Gate A PASS）

缺陷复现：旧逻辑只在"选中值为非 bool int 且超限"时拒绝；13 种非法形态中 11 种可绕过（修复前实测 21 failed）。

修复（冻结协议）：恰好一个有效输出上限字段（`max_tokens` 或 `max_completion_tokens`；同现须数值一致否则歧义拒绝）；值必须严格正整数；超限 403、非法/缺失/歧义 400；全部先于预算预留与上游发送，不耗预算；审计不含 key/prompt。

测试：13 参数化非法形态全部拒绝且 Fake Provider `call_count==0`、per_scope 为空；边界 1/2048/别名/同值对 200 通过（上游计数 4）；审计计数断言。

## P0-B：scope-aware UNKNOWN 对账（Gate B PASS）

缺陷复现：旧 `reconcile(scope)` 清除**全部** scope 的 UNKNOWN（修复前相关回归 failed）。

修复：运行+重放维护 `request_id->scope`；`reconcile(scope)` 只清本 scope；`reconcile_requests(ids, reason=)` 跨 scope 显式授权；replay 校验事件（越权/幽灵/无理由跨 scope/格式 → corrupt fail-closed）；历史费用与计数永不清零。

关键测试（两 scope 同时 UNKNOWN 的完整流程；现实路径=崩溃时多 scope 在途，种子账本构造）：reconcile(A) → 仍 stopped（剩 rid-B）、新请求 429、上游 0；reconcile(B) → 恢复 200；计数 {A:2,B:1} 不清零；**部分对账后重启，B 仍阻塞**（重放一致）。空 scope/幽灵 ID/空列表抛错。跨 scope 显式 IDs+reason 解除并留审计。

## P0-C：密钥隔离测试真实存在于 GitHub（Gate C PASS）

根因：`.gitignore` 第 6 行 `*secret*`（防密钥入库的保护规则）静默吞没 `tests/test_secret_isolation.py`；R1.3 提交差异中确无该文件，R1.3 报告路径失实（已在 R1.3 remediation 文档中加注更正）。

修复：改名扩展为 **`tests/test_credential_isolation.py`（9 项）**，`git check-ignore` 验证可提交，本次提交差异与远端 tree 可见；clean clone 内实际运行（P1-F）。

覆盖（均为真实请求构造/Runner 路径 + 捕获 subprocess，非对象属性/源码断言）：canary 真实 key 在 agent stdin JSON、docker argv/env、trace/ledger、stderr、provider 错误路径、**docker 启动失败异常文本**中 0 次出现；agent 仅持 per-run proxy token；live 构造强制 placeholder；`make_live_runner` 接线；`--live --out` 回归。

## P1-D：真实 key 不进 Docker CLI argv（Gate D PASS）

修复：`_docker(extra_env=)` 子进程环境注入 + 裸 `-e CE_PROXY_KEY` 透传；不落地任何文件。

测试：构造级捕获 `_docker` 入参——argv 无 canary、`-e` 后变量名无 `=`、`extra_env` 含 canary；docker run 失败异常文本无 canary。容器级：`docker exec printenv CE_PROXY_KEY == canary`（凭证送达）、`docker ps` Command 面无 canary、ledger 无 canary、proxy 功能正常。agent token 与上游 key 构造性相异。

## P1-E：重复事件语义一致性（Gate E PASS）

修复：RESERVED 重复的 scope/reserved_cny 不一致 → ledger corrupt；SETTLED cost 冲突 → corrupt；SENT/UNKNOWN 幂等。

测试：完全重复幂等通过、scope 冲突 corrupt、金额冲突 corrupt、非法转换/截断 corrupt；正常重启恢复回归全绿。

## 测试分类明细（实际执行命令 + 真实计数）

| 类别 | 命令 | 结果 | Docker |
|---|---|---|---|
| 预算/账本/上限/对账 | `pytest tests/test_budget_proxy.py tests/test_budget_proxy_r14.py -q` | 52 passed | 否 |
| 密钥/凭证隔离 | `pytest tests/test_credential_isolation.py -q` | 9 passed | 否 |
| 控制通道 | `pytest tests/test_proxy_control.py -q` | 8 passed | 否 |
| Docker E2E（含 key 送达、sibling 401、cap 上游计数） | `pytest tests/test_proxy_integration_e2e.py -q` | 7 passed | 是 |
| 算法适配器 + v2 驱动 | `pytest tests/test_causal_policy_adapter.py tests/test_phase4_v2_offline.py -q` | 19+7 passed | 部分 |
| **全量** | `pytest tests/ -q` | **523 passed / 0 failed / 0 skipped** | 部分真实参与 |
| Clean-clone（最终 SHA） | `python scripts/clean_clone_check.py` | 见末节实测 | 是（子集） |

无任何 skip 冒充 PASS；Docker daemon 与镜像全程可用；无可执行但被环境阻止而未报告的测试。

## 预算、费用与真实 API 调用

- 本轮新增 DeepSeek 模型 API 调用：**0 次**；费用：**¥0**。
- Fake Provider 实际接收计数（关键用例）：非法输出上限 13 形态 ×0；cap=1 E2E 上游恰 1 次；bridge sibling 攻击 ×0；reconcile 阻塞期 ×0。
- 未设置 `CE_DSH_LIVE_AUTH`；`--live` 未运行。

## Git 交付（P1-F：最终 SHA clean-clone 复验）

（推送后实测填写——完整 SHA、远端 SHA、clone HEAD、复算结果。）

## 冻结完整性

staged diff 中 `results/phase0–3`、`results/phase4/live`、benchmarks、冻结 src 模块零改动；密钥扫描 0 命中。

## 未解决问题 / NOT_VERIFIED

1. TUN 级 DeepSeek 直连仍为 DIRECT_ROUTE_UNVERIFIED（本轮 0 live 调用，无法实测路由）。
2. 多 scope 同时 UNKNOWN 的运行时路径只能靠"崩溃时多请求在途"产生（首个 UNKNOWN 即停止 gate）；测试用崩溃种子构造，已在代码注释说明。
3. `docker inspect` 的容器 Config.Env 仍可被本机特权用户读取 key（docker API 面，非 CLI argv）；已在文档标注，属宿主信任边界。
4. Planner 未在本机重跑测试；全部数字为 Executor 实际执行结果。

## 停止

停在 Phase 4 R1.4。未进入付费 pilot，未进入 Phase 5。
