# Executor Report — CE-DSH-P4-R1.6（溢出安全账本 / 计数更正 / 直连路由诊断）

日期：2026-10-21。Executor：Kimi。本轮**新增真实 DeepSeek 模型 API 调用 0 次、费用 ¥0**；未运行 `--live`；直连诊断**未发送任何 HTTP 数据或 API 请求体**。

计划：planner/latest_plan.md（CE-DSH-P4-R1.6）；审查：planner/reviews/CE-DSH-P4-R1_5-independent-review.md（R1.5 已验收，离线范围）。证据文档：docs/PHASE4_R1_6_REMEDIATION.md。

## A. Git 状态

- 起始 SHA：`a6e6b6e4490ba56ec67fe694fc307242fc8b1af3`（接管时工作区 clean）
- 最终 SHA / 远端 SHA / clean-clone 验证 SHA：见末节「Git 交付」

## B. 账本修复（P1-A，PASS）

- **根因**：`math.isfinite(10**400)` / `float(10**400)` 抛 `OverflowError`（本机 Python 3.10.1 实测），R1.5 的 `_valid_amount` 将异常泄漏进 `BudgetProxy.__init__`，启动以未处理异常中止而非受控 corrupt；`json.loads` 对超位数限制字面量可抛 `ValueError`（本运行时不限制，已实测），重放仅捕获 `JSONDecodeError`。
- **修改文件**：`src/causalevo/eval/budget_proxy.py`（`_valid_amount` 全域化 + 重放捕获 `ValueError`）。
- **修复方案**：金额校验对任意 JSON 值无异常——非 bool、数值、≥0，guard 下试转 float；转换失败或非有限即拒绝（金额必须可安全进入 float 记账表示）。数字解析失败 = 损坏账本。损坏账本：启动受控 `ledger_corrupt+stopped`、拒绝新请求、重启仍 fail-closed、**原始字节零改动**。
- **新增测试**：`tests/test_budget_proxy_r16.py` 7 项。
- **原始异常输入与实际结果**：`reserved_cny=10**400`、`cost_cny=10**400`、重复 SETTLED `10**400`、5000 位整数字面量 → 全部受控 corrupt（构造不抛异常）；`_valid_amount` 19 种样本（±10**400、NaN、Inf、bool、None、str、list、dict、±1e308、10**4300）无异常返回 bool。
- **修复前失败证据**：r16 首跑 `6 failed, 1 passed`（OverflowError 逃逸）。
- **重启后 fail-closed 证据**：每种异常种子账本 —— 代理 1：新请求 429；代理 2（同账本重启）：仍 429；测试前后账本文件字节一致。
- 合法历史（有限 int/float）精确恢复 known_cost=2.004；R1.4/R1.5 既有账本回归全部保持。

## C. 测试结果

| 项 | 命令 | 结果 |
|---|---|---|
| 新增 r16 | `pytest tests/test_budget_proxy_r16.py -q` | 7 passed |
| 预算三套件 | `pytest tests/test_budget_proxy.py tests/test_budget_proxy_r14.py tests/test_budget_proxy_r15.py tests/test_budget_proxy_r16.py -q` | 101 passed |
| 凭证/控制/e2e/适配器/v2 | 五文件联合 | 50 passed |
| **全量** | `pytest tests/ -q` | **574 passed / 0 failed / 0 skipped** |
| Docker | e2e 7 + v2 7 真实容器 | 通过（daemon 29.3.1 可用，无 NOT_VERIFIED） |
| clean-clone | 最终 SHA（见 Git 交付） | 见末节 |
| P1-B 计数 | `pytest tests/test_budget_proxy_r15.py --collect-only -q` | 42 = **21 别名（18 参数化 + 3 独立）+ 21 账本**；三处文档已更正，未增删测试 |

失败与重试：本轮全量一次通过，无失败重试；r16 修复前 6 failed 为缺陷复现（已修复并全绿）。

## D. TUN 直连诊断（无 HTTP）

- **实际代理/TUN 软件与模式**：Clash Verge + verge-mihomo（运行命令行实测）；运行时配置 `mode: global`、`tun.enable: false`（verge `enable_tun_mode: false`）；无 mihomo/wintun 活动适配器；Windows 系统代理 127.0.0.1:7897（仅作用于自愿客户端）；无 api.deepseek.com 规则条目。
- **DNS**：8 个公网 CDN IP。**TCP**：`api.deepseek.com:443` 连接成功。**TLS**：TLSv1.3，证书 CN=api.deepseek.com / TrustAsia DV TLS RSA CA 2025（真实边缘，无 MITM）；握手后立即关闭，零 HTTP 字节。
- **路由分类证据**：mihomo sidecar 连接日志在诊断时间窗（11:20–11:24）记录 **109 条**其他连接（均 using GLOBAL），**deepseek 条目 0 条** → 诊断连接未经过 mihomo；TUN 关闭（配置+无适配器）；代码层 `ProxyHandler({})` + 白名单固定 https 上游复核一致。
- **`DIRECT_ROUTE_UNVERIFIED` 是否解除**：**解除（限定口径）**——升级为 `DIRECT_ROUTE_VERIFIED`（本机/本时刻/直连 opener 路径；Sangfor aTrust 底层路由已注明为残余限制）。
- **是否发送 HTTP/API 请求**：**否**（仅 DNS 解析、TCP 连接、TLS 握手，握手后立即终止）。
- 本诊断**不构成**真实模型调用授权；live readiness 仍为 **NOT_READY**。

## E. 数据与安全

- **冻结数据哈希**：`results/phase0/live/calls.csv` SHA-256 = `1961bdd81a7f6a4ad4169d6f246530ed3df3170f70948f85de13ca136e364c59`（与记录一致）；`auditable_tasks.jsonl` = `35b9e67a418cfd55fd9e820ab48980750da7ab12d24bc61392768f24b27e4afa`；sweep 工件工作区 = `15e2cb844584398d5ce2e65c4ccb1c5bf6be052ab6436cee75815e14e4540ab4`（R1.5 记录的 CRLF/LF 规范化规则未变）。
- **历史数据是否变化**：`git diff a6e6b6e..HEAD -- results/ benchmarks/` 为空（本轮零冻结变更）。
- **密钥扫描**：`git diff --cached | grep -cE "sk-[A-Za-z0-9]{32}"` = 0；诊断过程未打印任何凭据（代理配置读取仅限模式/端口/规则字段）。
- **新增真实模型调用次数**：0。**新增费用**：¥0。新增测试不含任何真实 API 调用（r16 全为本地账本文件）。

## F. 未解决问题

1. Sangfor aTrust VNIC 处于 Up（企业 VPN 底层路由无法从用户态完全排除；TLS 端到端认证已通过，记录为残余限制）。
2. Planner 未在本机独立重跑测试；全部数字为 Executor 实际终端输出。
3. `docker inspect` Config.Env 对本机特权用户可见（既有宿主信任边界，未变化）。
4. live readiness：**NOT_READY**（无预算授权；直连诊断仅为工程就绪信号之一）。

## G. Git 交付（最终 SHA / clean-clone / 同步状态）

（push 后实测填写。）

## 停止

停在 Phase 4 R1.6。未进入付费 pilot，未进入 Phase 5。
