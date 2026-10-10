# Phase 1 R1 结果（全部离线，零 API 费用）

日期：2026-10-10。计划：CE-DSH-P1-R1。**本轮没有任何真实模型参与；fake agent 的结果只是工程管线证据，不是模型性能。**

## 1. 离线工程证据

- 测试：`pytest tests/ -q` → **123 passed / 0 failed / 0 skipped**（79 项 Phase 0 回归 + 44 项新增；含 Docker 对抗性隔离测试 7 项实跑）。
- 任务包：26 个确定性 microtask（13 train / 7 dev / 6 sealed_test，seed 20261010），生成器内置审计：每个 bug 版本必须至少失败一个 sealed check、参考修复必须通过全部 check（该审计实际抓获过一个编写错误：gcd 的"错误"版本原本逻辑正确）。
- 任务profile：`configs/dsh_task_patch.yml` 组合并引导成功（直接 exe 引导 exit 0）：无 shell/web/subagent/上传，仅 workspace 内 fs 工具。

## 2. 离线管线运行（26 任务 × 2 baseline，Docker 隔离执行器）

证据：`results/phase1/offline/<run_id>/{manifest.json, traces.jsonl, report.json}`。

| Policy | requested | executed | scored | visible pass | sealed pass | task_succeeded |
|---|---|---|---|---|---|---|
| B0-fixed-harness | 26 | 26 | 26 | 15 | 0 | **0** |
| B1-self-reflection-fixed-budget | 26 | 26 | 26 | 15 | 0 | **0** |

- fake agent 为 noop（不做任何修改）：0/26 是**诚实正确**的结果；15/26 的 visible 通过是设计使然（visible 检查故意宽松，sealed 才是判定）。
- oracle 模式（直接拷贝参考修复）在 `tests/test_pipeline_offline.py` 中验证 3/3 通过，证明 judge 能正确判对——仅为工程验证，不计入任何性能。
- 隔离执行：每命令一次性容器（`--network none`、只读根、256MB/1CPU/64pids、nobody 用户、硬超时 kill、退出即销毁）。对抗性测试（断网、宿主文件系统不可见、/work 只读、无继承密钥、超时 kill 无残留、内存上限）全部实测通过。
- Judge 盲化：judge 输入只有 workspace，不知道 policy；sealed tests 只在 judge 侧副本注入，agent workspace 内不存在。

## 3. 与计划验收门的对应

- P1-G1 ✅ 每任务独立客观 judge + 隔离 workspace；任务清单可复查（registry.json + 哈希钉死）；合成任务未冒充外部基准。
- P1-G2 ✅ 对抗性容器隔离测试实测通过；DSH profile 无 shell。
- P1-G3 ✅ B0/B1 预算平价锁定并有测试（`check_budget_parity`、配置-策略一致性）。
- P1-G4 ✅ 26×2 调度跑通；executed 与 task_succeeded 分列；fake 不误称成功。
- P1-G5 ✅ 123 全绿；seed/镜像/配置/任务哈希可复现。
- P1-G6 ✅ Phase 0 冻结 CSV 未触碰（哈希锁定测试继续通过）。
- P1-G7 ✅ 本轮零 live API 调用、零费用。
- P1-G8 待本次提交后由 SHA 核验完成。

## 4. 限制与未决项

1. LocalTrustedExecutor 的"只跑可信内容"是纪律约束而非 OS 强制；模型生成代码只允许走 DockerExecutor。
2. 外部基准（SWE-bench Verified 等）仅完成元数据审计，未下载未运行（见 docs/PHASE1_BENCHMARK_DECISION.md）。
3. RISK-1（无 id 等量 attempt 判重）在 live 重试启用前仍需专门 Gate；本轮离线无自动重试。
4. 真实 token 预算计量属 live 阶段事项，本轮预算为零。
