# Phase 1 R2 安全模型（CE-DSH-P1-R2-S0）

记录日期：2026-10-13。文中标注「2026-10-10 实测」的结论来自当日探针运行输出；其余为代码契约（以所引文件当前内容为准）。本文只做工程边界描述与残留风险登记：不构成 live 授权，不声称任何模型能力；fake provider 运行仅是管线工程证据。

## 1. 信任边界总览

四个世界，信任等级递减。核心原则：**模型可见的一切（prompt、工具、文件系统、网络出口）必须落在容器边界之内；宿主不再信任任何 runtime 自带沙箱。**

```
┌────────────────────────── 宿主（T0，信任域） ──────────────────────────┐
│ 凭据: DEEPSEEK_API_KEY / .env（仅宿主进程环境，不进镜像、不进挂载）      │
│ 仓库: benchmarks/tasks/**（含 sealed_tests / reference，已在 Git 公开）  │
│ 编排: agent_pipeline、RuntimeBudget、TaskTrace / RunManifest             │
│ FakeProvider: 仅绑定 127.0.0.1，离线零成本                               │
│ judge 侧副本 <ws>.judge：评分时短暂注入 sealed 测试，评完即删            │
└───────┬──────────────────────────────────────────────┬────────────────┘
        │ docker run（/work rw，bridge 网络）            │ docker run（/work ro，--network none）
        ▼                                              ▼
┌──────────── 任务执行容器（T1，唯一 agent 世界） ────────────┐  ┌────────── Judge 容器（T2） ──────────┐
│ 镜像 causalevo-dsh-agent:0.1.0（本地构建，vendored wheels） │  │ 镜像 python:3.11-slim，每命令一次性    │
│ DSH SDK/runtime 0.1.5rc1 + tool-fs + tool-fs-search        │  │ --network none / --read-only 根 fs   │
│ fs-sandbox + sandbox-policy = workspace-write              │  │ /work = judge 侧副本（只读挂载）      │
│ 仅挂载 /work（本任务 workspace 副本，rw）                   │  │ sealed/visible 测试只在此世界出现     │
│ 非 root（镜像内 USER agent）；768m/1cpu/128pids；--rm      │  │ nobody(65534)；256m/1cpu/64pids      │
└───────┬──────────────────────────────────────────────────┘  └──────────────────────────────────────┘
        │ 唯一网络出口：host.docker.internal（fake）/ api.deepseek.com（live，未授权）
        ▼
┌──────────────── Provider（T3，不可信外部服务） ─────────────┐
│ fake：宿主回环 FakeProvider（127.0.0.1，经 host.docker.internal 到达） │
│ live：api.deepseek.com —— 双重授权门未通过前禁止任何 socket（见 §6）    │
└────────────────────────────────────────────────────────────┘
```

| 主体 | 可读 | 可写 | 网络 |
|---|---|---|---|
| 宿主编排进程（T0） | 仓库、密钥、全部 workspace、judge 副本 | 仓库结果目录、workspace | fake 回环；live 需授权 |
| 任务执行容器（T1） | 仅 /work + 镜像内文件 | 仅 /work（workspace-write 拦截越界写） | bridge：fake 经 host.docker.internal；live 出口限制待实现（§6） |
| Judge 容器（T2） | 仅 /work（judge 侧副本，ro） | 无（--read-only 根 fs + ro 挂载） | 无（--network none） |
| Provider（T3） | 只收到请求体 | — | — |

补充：宿主上仍保留 `HostHarnessRunner`（src/causalevo/eval/harness_agent.py:115），仅供探针/调试，**不得用于任务执行**——原因见 §2。

## 2. 宿主 runtime 不是隔离边界（2026-10-10 实测）

计划 S0 的疑点：官方 `dsh-fs-sandbox` 在 workspace-write 策略下只限制 writes/edits，reads 是否穿透需要客观证据，不能用 prompt 禁止读取充当隔离。

实测（scripts/probe_fs_escape.py）：

- 在宿主直接启动 DSH runtime（HostHarnessRunner 同款路径），装配任务 profile `configs/dsh_task_patch.yml`（fs-sandbox + workspace-write 生效，shell/web 等已禁用）。
- fake provider 脚本驱动 agent 调用 `read`，参数为宿主 workspace 之外的绝对路径 `results/phase1/r2-scratch/HOST_CANARY.txt`。
- 结果：canary 内容 `HOST_SECRET_CANARY_7f3a9c` 被工具结果**完整逐字返回**（探针输出 `HOST CANARY LEAKED: True`）。

判定：fs-sandbox 的 workspace-write **只约束写**，读穿透成立。因此在宿主跑 runtime 时，agent 可读宿主任意文件（密钥、其他任务的 sealed/reference、凭据文件），仅禁用 shell+web 不构成边界。结论：**容器化是唯一的任务执行世界**；宿主 runtime 降级为 probe/debug 专用，并在 harness_agent.py 模块 docstring 与类 docstring 中明文标注「NOT an isolation boundary」。

## 3. 任务执行容器（ContainerHarnessRunner）实测边界

实现：src/causalevo/eval/harness_agent.py:211 `ContainerHarnessRunner` + docker/dsh-agent/（Dockerfile 以 digest 固定基础镜像，离线安装 vendored wheels，见 wheels/SHA256SUMS；入口 agent_entry.py 从 stdin 读单个任务请求，stdout 流式回传 JSONL 事件）。每任务一个一次性容器（`--rm`、唯一 `ceval-agent-<hex>` 名），仅挂载本任务 workspace 副本到 `/work`（rw），`DSH_HOME` 为容器内临时目录，随容器销毁。

2026-10-10 实测（scripts/probe_fs_escape_container.py，同一 canary、同一 patch profile）：

- 绝对路径读宿主 canary：容器内该 Windows 宿主路径不存在，读不到；
- `../` 目录穿越：读不到 canary；
- 对 `/` 做 grep 全局搜索：搜不到 canary；
- 三次攻击的工具结果均无 `HOST_SECRET_CANARY_7f3a9c`（探针输出 `HOST CANARY LEAKED: False`）；
- 越界写（/work 之外）被 workspace-write 策略拦截。

对抗性回归测试收于 tests/test_agent_fs_isolation.py，覆盖计划 S0 列出的 8 类：工作区外绝对路径读取、`../` 穿越、symlink/junction 穿越、Git 工作树上游 sealed/ref、其他任务目录、宿主 API key/.env、glob/grep 搜索宿主与 registry、写入越界；Windows 与 Linux 路径形态均覆盖。通过/失败证据以 results 与 `docs/PHASE1_R2_RESULTS.md` 为准，本文不代替运行记录。

资源与中止：768m 内存 / 1 cpu / 128 pids 上限；`RuntimeBudget` 的 wall-clock 与 tool-call 计数在事件流上实时生效，触发 `BudgetStop` 或超时即 `docker kill` 硬杀容器（harness_agent.py:321-325），超限在边界处中止而非事后发现。

正向功能同时被验证：同 profile 下 agent 对自身 /work 的 read/write 正常（scripts/smoke_container_bridge.py：脚本化 read→write→final，挂载 workspace 被真实改写）。

## 4. Judge 容器（独立评分世界）

`Judge.grade`（src/causalevo/eval/judge.py:53）在 agent 结束后运行：先在宿主把候选 workspace 复制为 `<ws>.judge`，将 sealed/visible 测试文件复制进该副本，再以 `DockerExecutor`（src/causalevo/eval/executor.py:53）起一次性容器执行——`/work` 只读挂载、`--network none`、`--read-only` 根文件系统、nobody(65534)、256m/1cpu/64pids、超时硬杀。评分前 `spec.verify_hashes()` 校验任务源包未被篡改（源包在容器边界外，agent 本无写途径）。判分结束后 judge 副本删除。

含义：候选代码（模型产物）只在无网络、只读、无密钥的容器里执行；sealed 测试只 transiently 出现在宿主信任域与 judge 容器，从不进入 agent 世界。judge 侧隔离的对抗性属性（无网络、无宿主文件、挂载只读、不继承宿主密钥、超时无残留容器、内存上限）由 tests/test_executor_isolation.py 锁定。

## 5. LocalTrustedExecutor：从纪律到程序守卫

R1 及以前，`LocalTrustedExecutor` 只靠「只跑可信内容」的文字纪律。R2 起改为程序守卫（src/causalevo/eval/executor.py:95-158）：

- 直接构造 `LocalTrustedExecutor()` 抛 `RuntimeError`；唯一入口是 `LocalTrustedExecutor.for_trusted_content()`，调用点即审计点；
- `default_executor(for_untrusted=True)` 在 Docker 不可用时抛 `ExecutorUnavailable`——fail-closed，不可信内容**永不降级**到宿主执行；
- 子进程环境最小化（仅 PATH/SYSTEMROOT/固定 PYTHONHASHSEED），不继承凭据；硬超时。

约束仍然成立：它只服务离线管线内的可信内容（reference fix、fake policy），任何模型产物路径的 executor 选择不得落入 local-trusted，live 模式亦然。

## 6. sealed/reference 数据分离与 holdout 声明

机制（已落地）：

- `WorkspaceFactory` 只复制任务包的 `workspace/` 子树（题目+可见测试+待修改代码）；tests/test_workspace_isolation.py::test_workspace_excludes_sealed_tests_and_reference 对全部 26 个 microtask 断言产物中无 sealed/reference 任何痕迹；
- sealed/reference 留在宿主 `benchmarks/tasks/**`，只在判分时注入 judge 侧副本（§4）；agent 容器挂载里物理上不存在这些文件——是文件系统缺席，而非「Python 对象字段没传给 agent」；
- `TaskTrace`/`AgentRunOutcome` 只保存 redacted 事件图（结构+逐事件 sha16，无文本正文）与 final response 的 sha16；不回传 policy_id、sealed 输出、reference patch、judge verdict 给 agent。

声明（科研有效性，非工程问题）：**26 个 microtask 的 sealed/reference 已在公开 GitHub 仓库中，对论文而言不是未见 holdout**，只能作工程 smoke。未来的独立 holdout 必须：不入 Git 的独立存储、访问有审查门槛、与方法调参隔离；在上游公开答案/sealed 元数据上不做方法级调参（计划 S4）。

## 7. live 模式遗留要求（授权前不得执行）

本轮红线：live 预算 ¥0，禁止一切真实模型请求。以下为进入任何 live pilot **之前**必须满足的条件，当前均为「要求」，非「已完成」：

1. **出口限制**：任务容器当前为 `--network bridge`（fake 模式需要经 host.docker.internal 到回环 provider）。live 模式必须改用仅放行 `api.deepseek.com` 的出口方案（专用 docker network + 代理/防火墙规则），并补 egress 测试；bridge 直通不满足 live 边界。
2. **密钥注入**：API key 经 stdin 请求 JSON 传入容器（harness_agent.py:244-254），不进镜像、不进环境变量、不进 /work、不落盘；容器内上传通道（session-telemetry-otel、session-log-deepseek）已被 profile patch 禁用（configs/dsh_task_patch.yml:119-123）。
3. **一次性授权门**：`require_live_authorization()`（harness_agent.py:199）要求 `DEEPSEEK_API_KEY` 与 `CE_DSH_LIVE_AUTH=phase1-pilot` 同时存在，缺一即在任何 socket 打开前抛 `PermissionError`；该授权为 Planner 单次发放，Phase 0 的 ¥10 不复用。

## 8. 残留风险清单

如实登记，按当前认知排序：

1. **bridge 网络的宿主面**：容器经 host.docker.internal 可到达宿主监听端口（fake provider 正赖此工作）。fake 模式可接受；live 前必须由 §7.1 的出口方案收敛，否则宿主任何监听服务都在 agent 可达面内。
2. **agent 容器根 fs 可写**：与 judge 容器不同，任务容器未加 `--read-only`（runtime 需写容器内临时 DSH_HOME）。缓解项是非 root 用户 + 无宿主挂载 + 容器一次性；残留是容器内持久化攻击面大于 judge 世界，但未观察到通向宿主的路径。
3. **容器内 `subprocess` 插件保持启用**：tool-fs-search 的 ripgrep sidecar 依赖它（dsh_task_patch.yml:22-26 注释）。它不向模型注册工具，shell 工具已全部禁用；残留是 runtime 进程能力面大于纯 fs 工具所需，属上游架构约束。
4. **approval policy=ask 与自动化运行**：profile 保留 approval 插件；非交互运行中的语义由 SDK 行为决定，未逐条审计其所有分支。fs 读写实测按预期放行/拦截，但更冷僻的工具路径未经穷举。
5. **Docker Desktop VM 边界**：Windows 宿主上真正的强制边界是 WSL2/Hyper-V 虚拟机与 dockerd。守护进程本身为特权组件；daemon 被攻破或镜像供应链（已用 digest+vendored wheels 缓解）属声明外威胁。
6. **sealed 测试的宿主瞬态**：判分时 sealed 文件短暂存在于宿主 `<ws>.judge` 目录（评完即删）。宿主是信任域，此窗口可接受；但若宿主被其他不可信进程共享则需重估。
7. **宿主 runtime 仍存在于代码库**：HostHarnessRunner 未被删除（探针/调试需要），误用风险靠 docstring 标注与评审把关；若未来它获得任务入口调用路径，须以测试封死。
8. **事件结构上游漂移**：DSH 为 Developer Preview，事件/usage 结构变化由解析器 fail-closed 处理（见 HARNESS_INTEGRATION.md），但新版本引入的工具面变化需在每次升级时重跑 §3 的全部对抗性测试。

---

边界判定汇总：宿主 runtime 读穿透（§2 实测）→ 任务执行唯一合法世界是 T1 容器；T1 对宿主 canary 的读/搜/写越界均被拒（§3 实测）；judge 世界只读无网（§4 实测+测试）；executor 选择 fail-closed（§5 代码契约）。满足以上，S0-Gate 的工程条件成立；live 仍需 §7 全部落地并获单独授权。
