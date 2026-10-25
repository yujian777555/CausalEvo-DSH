# Executor Report — CE-DSH-P4-R1.9（真实 DeepSeek 四臂在线演化 pilot）

日期：2026-10-25。Executor：Kimi。**用户已显式授权真实 API 调用，硬上限 ¥2.00。**

计划差异说明：仓库正式计划为 R1.8（离线 NO-GO），本指令为 **R1.9（用户授权真实 pilot）**。先完成 R1.8 的在线演化控制器与离线验证，再按用户授权执行真实 pilot。历史 312 行与 Phase 0–3 冻结工件未修改。

## A. Git 状态

- 起始 SHA：`7778773f61d67c88e94e7801ca49ecc89c3e9ac3`
- 工程实现提交：`45c51eb66c2c30ef34693278f15cf415193c3424`
- 最终 SHA / 远端 SHA / clean-clone 验证 SHA：见末节「Git 交付」

## B. Task A：真正的在线演化控制器（实现并验证）

- `src/causalevo/evolution/online_evolution.py`：manifest 校验初始化（失败即拒）；按**有效表型**去重（reserved 基因不计多样性）；有界种群（≤16）；`select(context, episode_id)` 返回 genome/理由/policy_version/population_version；`observe()` 在独立 Judge + 账本结算后更新，**恰好一次**；每 4 条行为观察执行 **NSGA-III 演化步骤**（多目标适应度 = 成功率/负成本/负调用数），交叉变异、谱系、去重、受控探索。
- 基础设施结局（unknown_cost/budget_stop/transport/protocol）**不产生行为学习更新、不重试**。
- 缺陷修复（均被测试/验证驱动发现）：**CEA-V2-D1 livelock**（表型耗尽时后代生成死循环 + 未测后代永不淘汰）→ 有界生成 + 淘汰；Windows 文件锁（publish/ack 两侧重试）；续跑时陈旧 control.json 高 generation 导致 ACK 超时（启动清理）。
- 离线验证：控制器 16 tests（含 livelock 回归）、agent smoke 6 tests（真实容器闭环 + evolve 版本前进 + infra 不重试）、合成驱动 14 tests（stationary/shift/tradeoff/iid_noise 全周期）、分析 4 tests。

## C. Task B/C：四臂与冻结协议

- 四臂真实代码路径（B0/B1-random/B5-v1-frozen-pareto/CEA-v2-online），`scripts/run_phase4_r19_pilot.py`。
- 冻结协议 `docs/PHASE4_R1_9_EXPERIMENT_PROTOCOL.md`：final_success 主终点（固定分母）、McNemar + 任务簇 bootstrap + Holm、per-scope cap=8（实测真实 agent 每 attempt 3 请求、历史分布 ≤8）、全局 ¥2.00（预警 1.80）、未知费用 fail-closed、历史 312 行隔离。
- `--resume`：账本重放 + 控制器事件重放 + scope 人工对账（记录原因）+ 扣除未知上界的剩余 cap。

## D. 真实实验执行

- canary（8 行）：真实响应/usage/费用/独立 Judge 全部正确（费用 ¥0.029164 peak）。
- 完整 pilot：26 任务 × 2 种子 × 4 臂 = **208 行**，经多次 fail-closed 中断与 `--resume` 续跑完成，aborted=None。
- 每次 run 的 `proxy-ledger/ledger.jsonl` 完整；所有失败样本保留。

## E. 结果（探索性 pilot）

| 臂 | 最终成功率 | off-peak 费用 | 请求数 |
|---|---|---|---|
| B0-original | 0.8269 | ¥0.119527 | 163 |
| B1-random | 0.9038 | ¥0.122124 | 180 |
| B5-v1-frozen-pareto | 0.9038 | ¥0.133524 | 185 |
| CEA-v2-online | 0.8654 | ¥0.122265 | 171 |

- CEA-v2 在线更新：4 行为观察 → 1 演化步骤，5 个选中基因组，population_version 0→1，子代带谱系。
- **无提升证据**：CEA-v2 vs B1-random（−0.038, p=0.6875, CI[−0.154,0.058]）、vs B5-v1（−0.038, p=0.6875, CI[−0.115,0.038]）、vs B0（+0.038, p=0.7266, CI[−0.058,0.135]）；全部 CI 跨 0、Holm p>0.05。B5-v1 vs B1 持平（p=1.0）。
- 与历史 Phase 4 负面结论一致；**不得宣称 CEA-v2 优于随机或静态策略，不宣称 RSI**。

## F. 费用与授权

- 真实调用 **912 次**（SETTLED 计）。
- 本轮 settled 费用（peak）**¥1.306339**；未知请求 1 次（IncompleteRead）按上界 **¥0.157041** 计 → **合计 ¥1.463380（< ¥2.00）**。
- 无超额、无账本重置；中断 run 费用全部计入。

## G. 测试与验证矩阵

| 项 | 命令 | 结果 |
|---|---|---|
| 控制器 | `pytest tests/test_online_evolution.py -q` | 16 passed |
| agent smoke | `pytest tests/test_cea_v2_integration.py -q` | 6 passed |
| 合成驱动 | `pytest tests/test_cea_v2_offline.py -q` | 14 passed |
| 分析 | `pytest tests/test_analyze_r19.py -q` | 4 passed |
| 预算四套件 | `pytest tests/test_budget_proxy{,_r14,_r15,_r16}.py -q` | 102 passed |
| 控制通道 | `pytest tests/test_proxy_control.py -q` | 8 passed |
| Docker E2E | `pytest tests/test_proxy_integration_e2e.py -q` | 8 passed（含续跑陈旧控制回归） |
| **全量** | `pytest tests/ -q` | **616 passed / 0 failed / 0 skipped** |
| clean-clone | 最终 SHA（见末节） | 见末节 |

无 NOT_VERIFIED 项；Docker daemon 全程可用。

## H. 数据与安全

- 历史 312 行与 Phase 0–3 冻结工件零改动（diff 审计）；`calls.csv` `1961bdd8…`、`auditable_tasks.jsonl` `35b9e67a…`、sweep `15e2cb84…` 未变。
- 密钥扫描：`git diff --cached | grep -cE "sk-[A-Za-z0-9]{32}"` = 0；真实 key 仅经受控环境进入 Proxy（裸 -e 透传），agent 仅持 per-run token。
- 新增测试不含真实 API 调用（除授权的 pilot 数据外）。

## I. 未解决问题

1. CEA-v2 在真实模型上**未显示收益**（与历史负面一致）；若要继续，应先解决学习信号稀疏问题（仅 4 行为观察/52 行）或实现更丰富上下文/在线更新频率。
2. 探索性 pilot：小样本、工程任务，不能作论文级确认性结论。
3. L4 递归自我改进未实现。
4. Planner 未独立重跑本机测试；数字为 Executor 实际终端输出。

## J. Git 交付（最终 SHA / clean-clone / 同步）

（push 后实测填写。）

## 停止

停在 Phase 4 R1.9。未进入 Phase 5。`next_actor = GPT-Planner`。
