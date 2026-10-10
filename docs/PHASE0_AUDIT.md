# Phase 0 审计（Executor 侧）

日期：2026-10-10。对应计划 CE-DSH-P0-R1 的 P0.1–P0.4 与验收门 G1–G8。

## 1. 来源与版本（Gate G1）

- 上游：github.com/deepseek-ai/deepseek-harness @ master `d743267388641bc76f17c45ce8b4c231aed1d32c`（git ls-remote，2026-10-10；最近上游提交 2026-10-09，Developer Preview 活跃变动中）。
- PyPI：deepseek-harness-sdk 0.1.5rc1（wheel sha256 `8d9897e9…`）、deepseek-harness-runtime-bin 0.1.5rc1（win_amd64 wheel sha256 `d031a5ab…`）。完整锁定见 `requirements-lock.txt`。
- 运行环境：Windows 11 原生 Python 3.10.1；runtime 为 wheel 内捆绑单文件 exe（`dsh --version` = 0.1.5-rc.1）。WSL Ubuntu-22.04（Python 3.10.12）作为已验证备用路径，未启用。
- 本机 pip 走清华镜像；Windows 注册表代理 (127.0.0.1:7897) 对 Python3.10 pip 会造成 TLS 错误，安装/运行均以 `NO_PROXY=*` 绕过（工程说明，不影响实验语义）。

## 2. 主要机制审计

### 2.1 工具与权限（P0.2 / G3）
- stock sdk profile 默认在 Windows 启用 `tool-pwsh`（持久 PowerShell）、fs/web/subagent 等 20+ 工具插件；`sandbox-policy` 默认 `workspace-write`。
- 基准以 profile patch（`configs/dsh_bench_patch.yml`）显式禁用全部工具/沙箱/子代理/工作流/技能/目标/计划/命令类插件，由 `tests/test_tool_disable.py` 做回归守卫。
- 实测依赖关系：`dsh-permission-presets` 等待 `shell`/`approval` 服务；`shell` 仅由 shell 工具插件提供，故 patch 同时禁用 `permission` 插件本身；`approval`、`shell-env` 保留（不向模型注册工具）。禁用后 runtime 正常启动（直接 exe 引导测试通过）。
- 额外纵深防御：`DSH_PERMISSION_MODE=read-only` 注入子进程环境。
- live 冒烟（2026-10-10）：12 个事件中无任何 tool 事件，模型单步直接作答，无工具目录出现在 request 事件中。

### 2.2 上传通道（P0.2）
- `session-telemetry-otel`：默认 OTLP 导出到 `https://harness-telemetry.deepseeksvc.com/v1/logs`（mode 默认 FEEDBACK_ONLY）→ patch 禁用。
- `session-log-deepseek`：planner 标记的会话日志上传插件 → patch 禁用。
- `web-search-deepseek` 复用 DEEPSEEK_API_KEY 做联网搜索 → patch 禁用（基准无网络工具需求）。
- session JSONL 持久化保留在本地隔离 DSH_HOME（gitignored），不进入模型输入以外的任何外发通道。

### 2.3 计量（P0.4 / G4）
- 互斥桶：uncached_input(inputTokens) / cache_read(cacheReadTokens) / cache_write(cacheWriteTokens，可选，上游本次未返回) / output(outputTokens，含 reasoningTokens)。
- settled usage：每个 assistant/message 事件的 data.usage（或最后一个 chunk:usage 帧）为该请求终值；分片不求和；多步 turn 的多个请求分别计费后求和。
- 重试与失败 attempt 单独记录（attempts 计数 + 各自 usage），成本永不忽略。
- 缺失/畸形 usage → fail-closed：标记 fail_closed、停止后续 live 调用、保留已发生成本（`tests/test_benchmark.py::test_missing_usage_fails_closed_and_stops_run`）。

### 2.4 价格与预算（P0.4）
- 价格表快照：官方价格页 2026-10-10（docs 记录 URL 与日期）；峰时 01:00–04:00、06:00–10:00 UTC 周一至周五（中国法定节假日除外），周末全天谷价。
- cache-write 无单独定价 → 按 miss 价计费并明确披露为上界，不等同 hit 价。
- 2026-10-10 为周六 → 全天 off-peak；报告同时给出 peak 口径上界。
- USD→CNY 7.10 为记录假设；实际对账以平台 /user/balance CNY 差值为准（live 运行前后各查一次）。
- 预算门控：每次新请求前要求「已花费 + 剩余计划 × 最坏单价 ≤ cap」，否则拒绝并安全退出；最坏单价按全部 miss + 满输出 + 峰价 + 允许重试计算。账单可能延迟，不宣称绝对不超支。

### 2.5 实验设计（P0.3 / G5）
- 四组各 25 次、固定生成器（`src/causalevo/scenarios.py`）、长度不变量测试锁定（`check_length_invariants`）。
- A 组同一 session 连发 → 历史长度混杂已标注；B 全新 session 同 prompt；C 同前缀变等长后缀；D 变靠前前缀（Bench-ID 字段位于前缀第 2 行，长度不变）同后缀。
- 组间 round-robin 交错（A,B,C,D 循环），执行顺序逐行记录在 calls.csv（position 列）。
- 全部调用固定：model=deepseek-flash、reasoningEffort=low、maxTokens=64、串行、无工具。

## 3. 风险清单（沿用 planner/review.md 并给出处置）

| 风险 | 处置 | 状态 |
|---|---|---|
| P0 Shell 权限暴露 / Key 泄漏 | patch 禁全部工具 + read-only + 隔离 DSH_HOME/workspace；密钥仅 env；脱敏测试 | 已缓解（live 证据见 PHASE0_RESULTS） |
| P0 忽略重试费用 / 误读互斥桶 / 虚构 live 数据 | 互斥桶解析 + 重试计量 + fail-closed + 失败注入测试 | 已缓解 |
| P1 System Prompt 变更与 session 长度混杂 | 全程固定配置；A 组混杂显式标注 | 已控制 |
| P1 工具 schema 频繁变化破坏缓存对照 | 无工具（空 schema），全 100 次恒定 | 已控制 |
| P2 账单颗粒度不足的成本偏差 | 双口径（peak 上界 + 分时）+ balance 差值对账 | 已披露 |
| 新增：上游 Developer Preview 不稳定 | 锁定 sdk/runtime-bin 0.1.5rc1 + 记录上游 SHA | 已缓解 |
| 新增：cacheWriteTokens 不上报 | 可选桶处理，分母仅含已上报桶，报告披露 | 已披露 |

## 4. 明确不做的事（G8）

本阶段不声称缓存优化已降低成本、不声称任何因果进化收益；PHASE0_RESULTS.md 仅报告测量值与混杂因素。
