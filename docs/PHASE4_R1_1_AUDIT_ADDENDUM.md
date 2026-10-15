# Phase 4 R1.1 审计增补（对 PHASE4_FINAL_EVALUATION.md 的只读补充）

日期：2026-10-14。本轮离线修复，**新增 API 调用 0，新增费用 ¥0**。原始负面结果与 312 行数据只读保留，未改写。

## 1. 证据恢复（Gate A）

- 本地原始 `tasks.jsonl`（312 行）存在；SHA-256 `21dd5dc09cae4f7d2647b3d7129942c37bd75c824d1619e86c2e10fb3c13bcbc`。
- 生成去敏可复算表 `auditable_tasks.jsonl`（schema_version=1，derived_from_sha256 记录，每行 row_sha16；无密钥/路径/原文/hidden oracle/CoT）。
- `.gitignore` 放行 `results/phase4/**/auditable_tasks.jsonl`；原始 tasks.jsonl 仍不追踪。
- `scripts/reconcile_phase4_rows.py`：从可复算表重算 pass rate / recovery / McNemar / bootstrap / 成本，与已提交分析**逐项相等**（实测通过）。
- CI 缺口修复：`tests/test_phase4_analysis.py` 等现在读取 auditable 表所在 run 目录；干净 clone 可复算。

## 2. 算法保真（见 PHASE4_ALGORITHM_FIDELITY_AUDIT.md）

旧臂真实语义：B4=启发式代理、B5=Pareto 选定静态 bundle。新 CausalPolicyAdapter（adapter_version="r1.1"）离线验证，不回填旧行。

## 3. 统计（Gate D）

- 保留 legacy_iid_paired 原值。
- 新增 task_id cluster bootstrap（26 簇，两种子同簇）：
  - B5 vs B0：[-0.0385, +0.1923]
  - B5 vs B1（随机对照）：[-0.1346, +0.0577]
  - B4 vs B5：[-0.1538, +0.0769]
- 全部 CI 跨 0；负面结论不变。B5 vs B0 存在 retry 预算混杂（B0 单次、B5 最多两次），仅作辅助。
- 种子只控制 B1 随机源与离线 RNG；DeepSeek 远端采样不可控（已列限制）。

## 4. DeepSeek Direct Connection Audit（补充要求）

- 代理类型：本机 Windows 全局注册表代理 127.0.0.1:7897（普通系统代理，非 TUN；TUN 无法从配置证明，见下）。
- 直连配置：
  - `balance.py` 与 `budget_proxy.py` 的上游客户端显式 `ProxyHandler({})`（空代理表）——urllib 层不读任何代理环境变量。
  - 容器内 `agent_entry.py` 的 `scrub_proxy_env()` 删除全部代理变量并钉住 `NO_PROXY=api.deepseek.com,127.0.0.1,localhost`。
  - 宿主与容器均不修改系统代理设置。
- 验证：`tests/test_direct_connect.py`（污染环境变量下 fake 上游仍 200；scrub 行为单测）；`tests/test_budget_proxy.py::test_no_env_proxy_honored_for_upstream`。
- **未解决**：若用户代理软件开启 TUN/透明模式，配置层无法证明路由绕过 → 该项标记 `DIRECT_ROUTE_UNVERIFIED`（需代理软件规则 `DOMAIN,api.deepseek.com,DIRECT` 或其连接日志确认；本轮无 live 调用，未做路由级验证）。
- GitHub 等其他服务的代理行为不受影响。

## 5. 历史修改痕迹

- PHASE4_EXPERIMENT_PROTOCOL.md 含 2026-10-15 口径澄清章节（agent attempt vs LLM 请求），记录为事后修订，不视为预先定义。

## 6. 费用声明

平台余额变动历史（2026-10-10 ¥4.83 → 2026-10-14 ¥3.77 → pilot 后 ¥3.03 量级）含本项目之外的因素；本阶段只声称"我们记录的调用成本"，不声称账户级完整对账。
