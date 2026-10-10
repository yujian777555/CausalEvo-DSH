# DeepSeek Harness 集成说明（Phase 0）

记录日期：2026-10-10。本文所有版本与 SHA 均为当日实测/实查。

## 上游版本固定（Gate G1）

| 组件 | 版本 / SHA | 证据 |
|---|---|---|
| 上游仓库 deepseek-ai/deepseek-harness | master `d743267388641bc76f17c45ce8b4c231aed1d32c` | `git ls-remote` 2026-10-10 |
| PyPI deepseek-harness-sdk | 0.1.5rc1（wheel sha256 `8d9897e9…b4d8`） | pypi.org JSON API |
| PyPI deepseek-harness-runtime-bin | 0.1.5rc1（win_amd64 wheel sha256 `d031a5ab…8acf`） | pypi.org JSON API |
| 捆绑 runtime | `dsh --version` → `0.1.5-rc.1` | 本机实测 |
| Python | 3.10.1（Windows x64 原生） | `py -3.10 -m venv` |

注意：SDK 是 Developer Preview；上游 master 仍在活跃推进（2026-10-09 有提交），版本不锁定则结果不可复现。

## 调用链

```
benchmarks/cache_benchmark.py
  └─ causalevo.runner.HarnessRunner
      └─ deepseek_harness.DeepSeekHarness (SDK 0.1.5rc1)
          └─ HarnessClient: 启动子进程 = 捆绑单文件 runtime exe
             (deepseek-harness-sdk-runtime-win-x64.exe --profile sdk --patch configs/dsh_bench_patch.yml)
             通过 stdio 以换行分隔 JSON-RPC 通信
              ├─ initialize {cwd, provider, model, reasoningEffort, maxTokens}
              ├─ session/prompt {sessionId, contentBlocks}
              └─ 通知流: session.event / session.status(idle) → RunResult(events, final_response, finish_reason)
                  └─ runtime 内部: Cordis 插件树 → deepseek-official adapter → api.deepseek.com
```

Session 生命周期：SDK 的 `Session.run()` 拥有从 prompt 落入持久 inbox 到整个 agent idle 的活动区间；session 事件 JSONL 持久化在 `DSH_HOME/sessions`（基准中指向隔离的 `results/phase0/*/dsh_home`，已 gitignore）。同一 `session_id` 再次 `run()` 即续接该 session（A 组依赖此语义）。

## 用量事件结构（2026-10-10 live 冒烟实测 + R1.2 契约补充）

实测（live smoke，真实服务端观测）：
- `request/header` 事件：`{config: {provider: "deepseek-official", model: "deepseek-flash", reasoningEffort: "low", maxTokens: 64}}`。
- `request/context` 事件：`{provider, model, contextWindow: 1000000, systemPromptUpdate: "in-history"}`。
- `assistant/message` 事件携带 settled usage：
  `{"inputTokens": 146, "outputTokens": 32, "totalTokens": 178, "cacheReadTokens": 0, "reasoningTokens": 21}`，
  位于 `data.usage`，且 `data.turn`/`data.step` 标识存在。
  - `inputTokens` = 未缓存输入，与 `cacheReadTokens` 互斥（与 planner/review.md 一致）。
  - **`cacheWriteTokens` 未返回**（可选桶，见 src/causalevo/usage.py 与计划 P0.4「如上游返回」）。
  - `reasoningTokens` 计入 `outputTokens`（32 = 21 reasoning + 11 text）。
  - 同一事件的 stream 末尾有 `chunk:usage` 帧，值与 `data.usage` 相同——同一次请求的分片不得重复累计。

代码契约（来自上游事件结构约定，**非真实 API 故障观测**，R1.2 起由构造 fixture 锁定解析语义）：
- `assistant/attempt`：失败/被重试的模型尝试可携带 settled usage（`data.usage` 优先，否则 `data.stream` 最终 `chunk:usage` 帧），即使从未提交 surface message。身份为 (turn, step, attempt id)。
- 去重规则：同一 (turn, step) 的无 id attempt 与已提交 message 用量相等 → 同一请求判重；用量不同 → 独立计费请求（如 provider 层重试）；身份缺失或冲突 → fail-closed。
- 系统提示词（`@deepseek-ai/dsh-system-prompt` 注入）：
  `You are an AI agent powered by DeepSeek Harness. / You are a coding agent powered by the deepseek-flash model. / Your working directory is <ws>`，
  另有每轮固定注入的运行时快照（Approval policy 说明）。两者在整个基准中字节恒定，构成被测稳定前缀的一部分。

## 模型 ID（Gate: 以已验证 wire id 为准）

- SDK 默认参数：`deepseek-v4-flash`（旧别名，官方价格页注明其请求由 DeepSeek-V4.1-Flash 服务并按 Flash 计价）。
- 本基准固定使用规范 wire id **`deepseek-flash`**，`GET /models`（2026-10-10）返回 `name: DeepSeek-V4.1-Flash`，`context_window 1048576`，`effort.supported_levels [low, high, max]`，default `high`。
- 基准固定 `reasoningEffort=low`（无 "none" 档位；low 最小化推理 token 开销）。

## 工具注册与禁用（Gate G3 的机制）

stock `sdk` profile 默认启用大量工具插件（Windows 上含 `tool-pwsh` 持久 PowerShell，以及 fs/web/subagent/workflow/skill 等）。`configs/dsh_bench_patch.yml` 通过 profile patch 将 50+ 插件显式 `disabled: true`（清单见 `tests/test_tool_disable.py` 的 DANGEROUS_IDS 回归守卫）。两个上传通道 `session-telemetry-otel`（默认 OTLP endpoint harness-telemetry.deepseeksvc.com）与 `session-log-deepseek` 亦被禁用。

依赖陷阱（实测）：`dsh-permission-presets` 依赖 `shell` 与 `approval` 服务；`shell` 服务只由 shell 工具插件提供。因此 patch 同时禁用 `permission` 本身，而 `approval`/`shell-env`（不向模型注册工具）保持启用。仅设 `DSH_PERMISSION_MODE=read-only` 或写 prompt「不要调用工具」都不构成隔离；补丁 + 冒烟实测（无任何 tool 事件、模型直接作答）才是证据。

## 隔离与密钥

- `DSH_HOME` 指向每次运行的隔离目录；runtime `cwd` 指向一次性空 workspace（`results/phase0/*/workspace`）。
- `DEEPSEEK_API_KEY` 仅从环境读取；密钥不落盘、不进日志/CSV/git（`tests/test_benchmark.py::test_no_key_material_in_any_output`）。
- 计费对账：`GET /user/balance`（CNY）在 live 运行前后各查一次，差值为实际计费基准。

## 已知限制

- `systemPromptUpdate: "in-history"` 能力存在（request/context 实测），但 SDK 公共接口未暴露逐字段的 prompt 更新测量；D 组只测「前缀字节变化的缓存损失」，不声称验证该功能（对应计划 P0.3 末尾说明）。
- Developer Preview 的 session 事件结构可能随上游版本变化；usage 解析器对结构变化 fail-closed。
