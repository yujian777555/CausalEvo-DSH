# CE-DSH-P4-R1.4 — Remediation Evidence（严格输出上限 / 按 scope 对账 / 可复现密钥隔离）

日期：2026-10-20。Executor：Kimi。本轮**新增 DeepSeek 模型 API 调用 0 次、费用 ¥0**；未运行 `--live`；历史冻结数据零修改。

计划：planner/latest_plan.md（CE-DSH-P4-R1.4）；审查：planner/reviews/CE-DSH-P4-R1_3-independent-review.md。

## P0-A：输出 token 上限严格 fail-closed

缺陷（审查 P0-A）：`max_out = obj.get("max_tokens", obj.get("max_completion_tokens"))`，仅当选中值为非 bool int 且超限时拒绝；缺失/null/字符串/浮点/负数/零/两字段冲突全部放行。

修复（`budget_proxy.py` 模块级 `_output_limit_problem` / `_validate_output_limit`，冻结协议写入注释）：

- 请求必须携带**恰好一个**有效输出上限字段：`max_tokens`（现行）或 `max_completion_tokens`（别名）；两字段同现仅在数值完全一致时视为一致，否则按歧义拒绝。
- 值必须为严格正整数：bool/float/str/null/缺失/负数/零一律非法。
- 超限（> worst_case_output_tokens）403；非法/缺失/歧义 400；全部发生在预算预留与上游发送之前，且不消耗预算。
- 审计：`_audit_reject("output_limit"/"output_limit_exceeds", body_sha16+bytes)`，不含 key、不含 prompt 原文。

测试（tests/test_budget_proxy_r14.py，缺陷复现先行：修复前 21 failed）：

- 13 种非法形态参数化（缺失、null、"256"、256.0、True、-5、0、1e9、别名 null/字符串/浮点、冲突对、错误类型对）：全部 400/403，Fake Provider `call_count == 0`，per_scope 为空。
- 边界正值：max_tokens=1、=2048（恰等于 cap）、别名=2048、同值对（64,64）→ 200，上游计数 4。
- 审计计数与无 prompt 文本断言。

## P0-B：scope-aware UNKNOWN 对账

缺陷（审查 P0-B）：`reconcile(scope=...)` 的 `cleared = sorted(self._unresolved_unknown)` 清除全部 scope 的未知请求；scope 仅是审计标签。

修复：

- 运行与重放均维护 `request_id -> scope`（`_request_scope`，RESERVED 时记录，replay 重建）。
- `reconcile(scope)` 只清除该 scope 的未决 UNKNOWN；其余 scope 继续阻塞全局 gate；空 scope 拒绝；无可决项为审计 no-op。
- 新增 `reconcile_requests(request_ids, *, reason)`：跨 scope 必须显式 ID 列表 + 操作理由；幽灵 ID/空列表/无理由拒绝；每项写 ledger（scope=None + scopes 列表 + reason）。
- 重放校验：reconcile 事件的 cleared 必须是存在的、未决的（RESERVED/SENT/UNKNOWN）request id；scope 不匹配（越权）、幽灵 ID、无理由跨 scope、格式损坏 → ledger corrupt，fail-closed。
- 解除后 gate 状态由剩余未决集合决定；历史费用与 scope 计数永不清零。

测试（真实驱动 + 账本种子；多 scope UNKNOWN 的现实路径是"崩溃时多个在途请求"，首个 UNKNOWN 会停止 gate，故两 scope 未决只能经崩溃恢复种子构造，注释已说明）：

- 运行时 500 → UNKNOWN → reconcile(本 scope) → 恢复。
- 两 scope 崩溃种子：reconcile(A) → 仍 stopped、剩余 rid-B、新请求 429、上游 0；reconcile(B) → 恢复 200；计数 {A:2,B:1} 不清零；重启后重放一致（部分对账后 B 仍阻塞）。
- 空 scope / 幽灵 ID / 空 ID 列表 → 抛错且仍阻塞。
- 跨 scope 显式 IDs + reason → 解除；ledger 含 reason 审计。
- 重放拒绝：越权 scope 的 reconcile 事件、幽灵 ID reconcile 事件 → corrupt。

## P0-C：密钥隔离测试真实存在于 GitHub

根因：R1.3 的 `tests/test_secret_isolation.py` 被 `.gitignore` 的 `*secret*` 保护规则（第 6 行，防真实密钥入库）静默吞没，从未进入远端 tree；R1.3 报告路径失实。

修复：

- 改名并扩展为 **`tests/test_credential_isolation.py`**（不绕过保护规则），`git check-ignore` 验证可提交。
- 9 项测试：canary 真实 key 经真实请求构造/Runner 路径（捕获 subprocess）：stdin 请求 JSON、agent docker argv/env、trace/ledger 序列化、stderr 0 次出现；provider 错误路径与 **docker 启动失败异常文本**同样 0 次；live 构造缺 endpoint/placeholder → ValueError；`make_live_runner` 工厂接线；源码守卫；`--live --out` 回归。
- P1-D argv canary（见下）也在本文件：ProxyContainer docker-run 构造级捕获。
- 报告与 status.json 路径已统一更正；clean clone 中实际运行（P1-F）。

## P1-D：真实 key 不进 Docker CLI argv

缺陷：`env += ["-e", f"CE_PROXY_KEY={key}"]` 使真实 key 成为宿主 docker CLI argv 一部分。

修复（`networks.py`）：

- `_docker(..., extra_env=...)`：密钥只经子进程**环境变量**传递。
- ProxyContainer 改用裸 `-e CE_PROXY_KEY` 透传（argv 只有变量名没有值）。

测试：

- 构造级 canary（tests/test_credential_isolation.py）：捕获 `_docker` 实际入参——argv 任何元素不含 canary，`-e` 后的 `CE_PROXY_KEY` 无 `=`；`extra_env["CE_PROXY_KEY"] == canary`（凭证送达）；docker run 失败（rc=125）的异常文本不含 canary。
- 容器级（tests/test_proxy_integration_e2e.py）：`docker exec <proxy> printenv CE_PROXY_KEY` == canary；`docker ps` Command 面不含 canary；ledger 序列化不含 canary；proxy 功能正常。
- agent token 与上游 key 构造性相异断言。

## P1-E：重复事件语义一致性

缺陷：同 request_id 同 state 的重复只校验 SETTLED cost；冲突 RESERVED（scope/reserved_cny 不同）被静默幂等。

修复（replay）：RESERVED 重复必须 scope 与 reserved_cny 完全一致（含 legacy task_id 键归一），否则 ledger corrupt；SETTLED cost 冲突 corrupt（已有）；SENT/UNKNOWN 无语义字段，幂等。

测试：完全重复幂等通过、scope 冲突 corrupt、金额冲突 corrupt、非法转换 corrupt、截断日志 corrupt（既有）、正常重启恢复不受影响（既有回归全绿）。

## P1-F：最终 SHA clean-clone

`scripts/clean_clone_check.py` 的 clone 内测试扩展为：

- 统计复算：reconcile_phase4_rows.py + test_phase4_analysis/integrity/auditable；
- 关键套件：test_credential_isolation、test_budget_proxy、test_budget_proxy_r14、test_proxy_control、test_proxy_integration_e2e（Docker）、test_causal_policy_adapter、test_phase4_v2_offline（Docker）。

最终 SHA 的实际执行结果记录在 planner/executor_report.md 的 Git 交付节（完整 SHA，非短 SHA）。

## 边界

Phase 0–3 与 2026-10-14 的 312 行真实数据零改动；本轮 0 次真实模型调用、¥0；fake-provider 结果不构成模型效果证据。
