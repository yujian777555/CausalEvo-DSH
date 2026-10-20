# CE-DSH-P4-R1.3 — GPT Planner 独立复审

- 审查目标：远端 `main` HEAD `9b1abcb18cdbe13700315a9ff101f5f8e41515ee`
- R1.3 主提交：`1ae933a48623da26d6941e051da4157fa25bd3e7`
- 结论：**CHANGES_REQUESTED**。R1.3 有实质进展，但不能授权真实 API pilot。
- 方法：复核 GitHub main 的文件树、提交差异、预算代理、网络/容器入口、实验驱动、测试与 status。Planner 未在 Executor Windows/Docker 主机重新执行 496 项测试，以下 PASS 数字仍是 Executor 报告，不是 Planner 独立运行结果。
- 本轮 Planner 无真实 DeepSeek 调用；新增 API 调用与费用均为 0。

## 已确认的进展

1. `ContainerHarnessRunner` live 构造现在要求 endpoint 和显式 placeholder；`run_phase4_pilot.py` 不再把真实 key 写入 agent-facing holder。静态调用链较 R1.2 明显改善。
2. `BudgetProxy._replay` 现在重建 SETTLED 费用和 scope 计数，未结算/UNKNOWN 默认阻塞，损坏 ledger 采取 fail-closed。
3. Proxy ingress 有独立 token、上游 host allowlist/HTTPS 检查和 provider-side request counter。
4. CEA-v1 artifact 使用独立 manifest pin；新 v2 driver 有四种 fake-provider 场景，且将结果标注为 `adapter_integration_smoke`，没有把它当作算法效果。
5. 真实 312 行历史 pilot 数据没有在本轮提交差异中被改写。

## P0 — 阻止真实 API pilot

### P0-A：输出 token 上限验证可绕过

源码：`src/causalevo/eval/budget_proxy.py:363-369`

当前逻辑：

```python
max_out = obj.get("max_tokens", obj.get("max_completion_tokens"))
if isinstance(max_out, int) and not isinstance(max_out, bool) and max_out > cap:
    reject()
```

当两个字段都缺失、选中字段为 `null`、字符串、浮点数或负整数时，条件不成立，请求会继续进入预算预留和上游转发。尤其是缺失 output cap 时，代理仍按固定 `worst_case_output_tokens` 预留，无法证明上游实际生成量被同一上限约束。

修复要求：
- 必须存在且只允许一个明确的输出 token 限制字段（按冻结的 DeepSeek SDK 请求 schema 选用）。
- 值必须是严格正整数，拒绝 bool、float、string、null、缺失、负数/零及超限值。
- 若两个别名同时出现，按冻结协议拒绝歧义请求，除非已证明其语义和数值一致。
- 所有拒绝都发生在任何 upstream 请求之前；Fake Provider 计数必须为 0。
- 新增覆盖缺失、null、字符串、float、bool、负数、零、超限、两个字段冲突的测试。

### P0-B：`reconcile(scope=...)` 实际解除所有 scope 的 UNKNOWN

源码：`src/causalevo/eval/budget_proxy.py:235-250`

方法记录了调用方的 `scope`，但 `cleared = sorted(self._unresolved_unknown)` 会清除所有未解决请求，并把全局 `_stopped` 解除。scope 当前只是审计标签，没有作为筛选条件。

这会导致只对 scope A 做人工核对，却同时解锁 scope B 的未知费用请求。它违背了 R1.3 声称的 scoped reconcile 语义。

修复要求：
- 重建并持久化 `request_id -> scope` 映射。
- `reconcile(scope=...)` 只能解除指定 scope 的未知请求；其他 scope 的 UNKNOWN 必须继续阻塞全局 gate。
- 如需跨 scope 清理，要求显式列出 request IDs 和授权理由，逐项写入 ledger；不能用默认 scope 隐式全清。
- 重启后重放 reconciliation 时，只认可事件中明确列出的 request IDs，并验证这些 IDs 属于被授权 scope。
- 测试 A、B 两个 scope 同时存在 UNKNOWN：reconcile A 后 B 仍阻止新请求；reconcile B 后才可继续。历史费用和请求计数不得清零。

### P0-C：密钥隔离的声称测试文件不存在于远端

`status.json` 与 `planner/executor_report.md` 声称 `tests/test_secret_isolation.py` 7/7 通过；但在当前远端 HEAD 的完整 Git tree 和 R1.2→R1.3 文件差异中均找不到该文件。相关实际存在的 `tests/test_direct_connect.py` 只有构造/配置级检查，未提供报告所声称的 7 项完整 canary 测试证据。

源码结构显示 live runner 的 placeholder 逻辑已经改进，但该关键 Gate 的报告和可复现证据不一致，故不能独立验收为 PASS。

修复要求：
- 将 secret-isolation 测试实际提交到远端，或如确有等价测试，准确更正报告中的路径、命令和用例数。
- 必须通过真实 request-builder/run path 注入 canary key，检查 agent stdin JSON、agent Docker argv/env、trace、异常与日志中均不含真实 key，并验证代理上游凭证仍正常注入。
- 以最终 HEAD 在 clean clone 中运行该测试；测试文件必须在远端 tree 可见。不得仅用源码字符串断言代替行为测试。

## P1 — 必须补齐

### P1-D：真实上游 API Key 被放进 Docker CLI 参数

源码：`src/causalevo/eval/networks.py` 中构造 `env` 的部分：

```python
env += ["-e", f"CE_PROXY_KEY={self.upstream_api_key}"]
proc = _docker("run", ..., *env, ...)
```

真实 API key 因而成为宿主端 Docker CLI 子进程的命令行参数。它虽未进入 Agent 容器，但可能暴露给本机进程命令行检查、进程采集或诊断日志，与“密钥只进入可信 Proxy”目标不够一致。

修复要求：通过受控 subprocess environment + `docker run -e CE_PROXY_KEY`（不在 argv 写值），或其他经过审计的安全注入机制传递。新增 canary 测试，确保 Docker 命令参数、异常和日志不含 key，同时 Proxy 容器能读取正确凭证。不要将 key 写入普通 Git 文件或未保护的临时文件。

### P1-E：重复 RESERVED 等同状态事件的冲突没有被完整检测

源码：`src/causalevo/eval/budget_proxy.py:169-178`

相同 request_id 和相同 state 时，当前只有 SETTLED 重复事件检查 cost；重复 RESERVED 若 scope 或 reserved_cny 不同，会直接被当作幂等重复跳过。报告称 ledger 冲突重复 fail-closed，但实际实现只对重复 SETTLED 的费用冲突作检查。

修复要求：对同状态重复事件按其语义字段验证幂等一致性。重复 RESERVED 的 scope/reserved_cny 不同必须标记 ledger corrupt 并停止；不能把冲突记录静默吞掉。增加针对性回归测试。

### P1-F：clean-clone 最终 SHA 证据过期

Executor 报告的 clean-clone 输出是 `HEAD 1ae933a48623 == origin/main`，但最终远端 HEAD 是 `9b1abcb18cdbe13700315a9ff101f5f8e41515ee`。随后 housekeeping commit 新增了一个旧版 v2 run 的 records 文件。该变化不一定影响源码，但报告没有证明 clean-clone 检查针对最终 HEAD `9b1abcb...` 执行。

修复要求：在最终提交推送完成后，对精确的最终 SHA 重新执行 clean-clone；报告必须记录完整 SHA、远端 SHA、实际 clone HEAD 和重算结果。之后如再有提交，重新执行或明确声明该提交未经过最终 clone Gate。

## 当前 Gate 结论

| Gate | Planner 判断 |
|---|---|
| 密钥不进入 Agent | 实现结构有改善；声称的 canary 测试缺失，NOT_VERIFIED |
| 预算重启恢复 | 静态实现改善；Executor 报告 PASS，Planner 未重跑 |
| scoped reconciliation | **FAIL：实际全局清除 UNKNOWN** |
| Proxy 入口认证 | 静态实现与报告相符，Planner 未重跑容器测试 |
| 输出 token 上限 | **FAIL：缺失/非整数值可能绕过** |
| CEA-v0/v1 fake adapter smoke | 已有新证据，但仅为集成 smoke，不是算法效果 |
| Clean-clone 最终 SHA | **NOT_VERIFIED：报告 SHA 早于最终 HEAD** |
| 真实 API 调用 | 0；不得据此推断 TUN 级直连已验证 |

**最终决定：CHANGES_REQUESTED。R1.3 不验收，不批准 live pilot。下一步 CE-DSH-P4-R1.4，仍然只做离线修复，新增 DeepSeek 模型调用 0 次、费用 ¥0。**
