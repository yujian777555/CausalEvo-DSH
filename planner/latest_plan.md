# CE-DSH-P4-R1.4 — Strict Output Bounds, Scoped Reconcile & Verifiable Secret Isolation

Planner baseline: `9b1abcb18cdbe13700315a9ff101f5f8e41515ee`

独立审查：`planner/reviews/CE-DSH-P4-R1_3-independent-review.md`

本轮只修 R1.3 复审发现的问题并补齐可复现证据。**新增真实 DeepSeek 模型 API 调用 0 次，新增预算 ¥0。** 不运行 `--live`，不查真实余额，不进入 Phase 5。

## 0. 接管

- fetch `origin/main`，确认远端 HEAD。
- 阅读本计划、R1.3 复审、status.json、executor_report.md 和 remediation report。
- 保护所有未提交改动；以当前 GitHub 代码为准。
- 保留 Phase 0–3 与 Phase 4 历史 312 行真实记录及 SHA，不覆盖或回填。

## P0-A：输出 token cap 必须严格 fail-closed

文件：`src/causalevo/eval/budget_proxy.py`

- 在任何预算预留和上游发送前解析 output limit。
- 按冻结的 DeepSeek chat-completions schema 选择允许的字段；必须存在且严格为正整数。
- 拒绝缺失、null、字符串、浮点数、bool、负数、0、超过上限。
- 如果 max_tokens 与 max_completion_tokens 同时出现，拒绝歧义组合，除非协议已明确规定且实现验证它们一致。
- 任何验证失败写入不含 key/prompt 的拒绝审计，不能预留预算、不能访问上游。
- 测试逐项覆盖上述异常值；使用 Fake Provider 的独立接收计数证明每项违规请求 upstream count = 0。
- 保留正常边界值恰好等于 output cap 时的正向测试。

## P0-B：scope-aware UNKNOWN reconciliation

文件：`src/causalevo/eval/budget_proxy.py`

- 在内存状态和 ledger replay 中保存 `request_id -> scope`。
- 修复 `reconcile(scope=...)`：只能清除指定 scope 下已列明的 UNKNOWN 请求，不能清空整个 `_unresolved_unknown` 集合。
- 若需要跨 scope reconcile，要求显式 request ID 列表、操作理由和人工授权记录；拒绝空 scope、默认全清或不存在的 ID。
- 重放时验证 reconcile event 中 request IDs 与 scope 对应；冲突、越权或格式损坏 fail-closed。
- 解除 scope A 后，scope B 未知请求仍使全局 gate 保持停止；不得因为 A 已确认就允许请求越过 B 的未知费用风险。
- 测试至少覆盖两个不同 scope 同时 UNKNOWN、先只 reconcile A、重启后仍保留 B 的 UNKNOWN、再 reconcile B 的完整流程。
- 历史已知费用、各 scope 请求数和未知请求审计不得清零。

## P0-C：密钥隔离测试必须真实存在于 GitHub

- 修正 `status.json` 与 `planner/executor_report.md` 中声称存在但远端缺失的 `tests/test_secret_isolation.py` 证据。
- 新增该测试文件，或在确有等价测试时统一路径/命令/用例数；优先提交独立、易运行的 `tests/test_secret_isolation.py`。
- Canary key 必须经过实际 request construction / runner path，而不是仅测试对象属性。
- 断言真实 key 不出现在 Agent stdin JSON、Agent Docker argv/env、trace、stdout/stderr、异常和日志中。
- 断言请求内只使用 per-run proxy client token，Fake Provider 端仍由 Proxy 注入正确的 trusted upstream key。
- 对错误路径、Docker 启动失败和 provider 错误同样检查。
- 在最终 clean clone 中运行测试，并确认该测试路径在 GitHub tree 和提交差异中存在。

## P1-D：避免真实 key 出现在 Docker CLI argv

文件：`src/causalevo/eval/networks.py` 及 Docker helper。

- 当前 `-e CE_PROXY_KEY=<real-key>` 把 key 值放进 docker CLI argv。
- 改为受控 subprocess environment + `docker run -e CE_PROXY_KEY`（argv 不包含值），或经过审计的等价安全注入方式。
- 不把 key 写入 Git 跟踪文件或无保护临时文件。
- Canary 测试验证：Proxy 进程确实得到正确 key；Docker CLI argv、异常和日志中没有 key。
- 代理 client token 与上游 key 必须继续分离。

## P1-E：ledger 同状态重复事件完整性

文件：`src/causalevo/eval/budget_proxy.py`

- 重复事件只在语义字段完全一致时才可视为幂等。
- 重复 RESERVED 的 scope/reserved_cny 不同必须标记 ledger corrupt 并 fail-closed。
- 对其他同状态事件校验所有有意义字段；不能仅校验重复 SETTLED cost。
- 增加合法完全重复事件通过、冲突 RESERVED、冲突 SETTLED 及截断日志拒绝的测试。

## P1-F：最终 SHA 的 clean-clone 复验

- 完成所有修改后先 commit/push。
- 确认最终本地 HEAD == `git ls-remote origin main`。
- 使用该精确 SHA 重新运行 clean-clone；报告完整 SHA，不得只报告短 SHA。
- 在 clean clone 中运行统计复算和关键测试（secret isolation、budget proxy、control channel、proxy E2E、CEA adapter smoke）。
- 如果验证后再产生任何提交，必须重新运行最终 SHA Gate，或如实声明新提交未经 Gate 验证。

## Gate

A. 缺失/非法/超限 output limit 全部在上游发送前拒绝。
B. scope A 的 reconcile 不解除 scope B 的 UNKNOWN；重启后状态仍一致。
C. GitHub 存在并可执行真实 canary secret-isolation 测试。
D. Docker CLI argv、日志、异常不含真实 upstream key；Proxy 收到凭证且能通过 Fake Provider 鉴权。
E. ledger 的冲突重复事件 fail-closed。
F. 最终 HEAD 与 origin/main 完全一致，最终 SHA 的 clean-clone 复算成功。
G. Phase 0–3 与历史 312 行实验数据零改动。
H. 本轮真实 DeepSeek 模型 API 调用 0 次、费用 ¥0。

任意 P0 未通过：`phase_status=BLOCKED`。全部 Gate 通过后：`phase_status=READY_FOR_REVIEW`、`next_actor=GPT-Planner`。推送后停止等待 Planner，不得启动 live pilot。
