# CE-DSH-P4-R1.6 — Remediation Evidence（溢出安全账本 / 计数更正 / 直连路由诊断）

日期：2026-10-21。Executor：Kimi。本轮**新增 DeepSeek 模型 API 调用 0 次、费用 ¥0**；未运行 `--live`；直连诊断**未发送任何 HTTP 数据/API 请求体**。

计划：planner/latest_plan.md（CE-DSH-P4-R1.6）；审查：planner/reviews/CE-DSH-P4-R1_5-independent-review.md（R1.5 已验收，离线范围）。

## P1-A：超大金额账本解析 fail-closed（PASS）

根因（审查 §Non-blocking robustness）：

- `math.isfinite(10**400)` 与 `float(10**400)` 抛 `OverflowError`（本机 Python 3.10.1 实测），R1.5 的 `_valid_amount` 会把异常泄漏到 `BudgetProxy.__init__`，启动以未处理异常中止，而非受控 `ledger_corrupt`。
- `json.loads` 对超过运行时整数位数限制的字面量可抛 `ValueError`（本运行时 3.10.1 无该限制，已实测确认；代码仍防御有此限制的运行时）。

修复（`budget_proxy.py`）：

- `_valid_amount` 改为**对任意 JSON 解码值完全无异常**：非 bool、数值类型、≥0，然后在 guard 下尝试 `float(v)`；转换失败（OverflowError/ValueError/TypeError）或结果非有限 → 拒绝。金额必须能安全进入 float 记账表示。
- 账本重放的逐行 `json.loads` 在 `JSONDecodeError` 之外增加 `ValueError` 捕获（数字解析失败 = 损坏账本）。
- 损坏账本：启动后 `ledger_corrupt + stopped`、拒绝新请求、重启后仍 fail-closed、**原始字节零改动**（测试前后字节一致）；合法账本重放/崩溃恢复/幂等/scope 对账语义全部保持。

测试（tests/test_budget_proxy_r16.py 7 项；修复前 6 failed，含 10**400 构造时 OverflowError 逃逸）：

- `reserved_cny=10**400`、`cost_cny=10**400`、重复 SETTLED `10**400` → 受控 corrupt（构造不抛异常）。
- 数字位数字面量：本运行时不限制 → 5000 位字面量解析后由校验器判 corrupt；对有限制的运行时按 limit+10 位构造（代码路径已覆盖，文档注明）。
- 正常有限 int/float → 合法记账（known_cost 精确恢复 2.004）。
- `_valid_amount` 全域性：19 种样本（含 ±10**400、NaN、Inf、bool、None、str、list、dict、±1e308、10**4300）不抛异常且返回 bool。
- 损坏账本新请求 429、重启 429、文件字节不变。

## P1-B：R1.5 测试分类计数更正（PASS）

实测命令与结果：

```
$ pytest tests/test_budget_proxy_r15.py --collect-only -q
42 tests collected
per-function: test_alias_fields_individually_strict 18, test_alias_pair_valid_equal_ints_passes 1,
  test_alias_pair_conflicting_valid_ints_rejected 1, test_both_alias_fields_missing_rejected 1,
  test_duplicate_settled_* 5+1, test_initial_settled_* 4, test_initial_reserved_* 4,
  test_duplicate_reserved_* 5, test_corrupt_ledger_refuses_* 1, test_valid_history_* 1
=> 输出 token 别名组 21 + 账本数值组 21 = 42
```

初版报告按 20+22 拆分系误写（总数 42 一致）；已更正 planner/executor_report.md、status.json、docs/PHASE4_R1_5_REMEDIATION.md；未为对齐文档增删测试。

## P1-C：Windows 全局代理/TUN 直连诊断（无 HTTP）

### 实际代理环境（实测，非推测）

- 软件：**Clash Verge（clash-verge.exe，tauri 壳）+ verge-mihomo 核心（PID 11668）**；运行命令行：`verge-mihomo.exe -d <AppData verge dir> -f <dir>\clash-verge.yaml -ext-ctl-pipe \\.\pipe\verge-mihomo`。
- 系统代理：Windows 注册表 ProxyEnable=1，ProxyServer=127.0.0.1:7897（mihomo mixed-port）；本 shell env 亦有 HTTP(S)_PROXY/ALL_PROXY=127.0.0.1:7897、NO_PROXY 仅 localhost（**不含** api.deepseek.com）。
- 运行时模式（clash-verge.yaml）：`mode: global`；`tun.enable: false`；verge `enable_tun_mode: false`、`enable_system_proxy: true`。**TUN 未启用**；Get-NetAdapter 无 mihomo/wintun 活动适配器。
- 规则集中**无 api.deepseek.com 条目**；global 模式下仅"自愿使用系统代理的客户端"被全部代理；不使用代理的客户端不经 mihomo。

### 直连诊断（2026-10-21T11:22:11 本地时间；零 HTTP 字节）

1. DNS：`api.deepseek.com` → 8 个公网 CDN IP（如 1.71.87.129、123.182.162.200 …）。
2. TCP：`api.deepseek.com:443` 连接成功（peer 1.71.87.129）。
3. TLS：TLSv1.3 `TLS_AES_256_GCM_SHA384`；证书 `CN=api.deepseek.com`，签发者 `TrustAsia DV TLS RSA CA 2025`，SAN=[api.deepseek.com]，有效期至 2026-12-01——**终结于真实 DeepSeek 边缘，无 MITM**。握手后立即关闭，未发送任何 HTTP 数据。
4. **连接级路由证据（决定性）**：mihomo sidecar 连接日志在 11:20–11:24 窗口记录 **109 条**其他 TCP 连接（chat.openai.com、chatgpt.com、telemetry-logs.kimi.com 等，均 "using GLOBAL"），其中 **api.deepseek.com 条目 = 0**——我们的诊断连接（11:22:11）确实未经过 mihomo。
5. 代码层复核：`budget_proxy.py` 上游 opener = `urllib.request.build_opener(urllib.request.ProxyHandler({}))`（忽略 env/系统代理）；上游 URL 冻结于配置白名单（live 仅 `https://api.deepseek.com`），无重定向入口。

### 结论

**DIRECT_ROUTE_VERIFIED（限定口径）**：在本机、本时刻、直连 opener 路径上，`api.deepseek.com:443` 不经 mihomo/TUN——证据链：TUN 配置关闭 + 无 TUN 适配器 + 连接日志活跃但零 deepseek 条目 + 真实 CA 证书。

保留限制：Sangfor aTrust VNIC 处于 Up（企业 VPN 底层路由无法从用户态完全排除，但 TLS 端到端认证已通过）；本结论**不构成**任何真实模型调用授权（仍需 Planner 与预算授权）。

## 验证矩阵与冻结审计

见 planner/executor_report.md（全量测试、clean-clone 最终 SHA、冻结哈希、密钥扫描）。
