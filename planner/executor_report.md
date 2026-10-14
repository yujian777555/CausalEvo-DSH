# Executor Report — Phase 3.1 Causal Evolution Algorithm Foundation（CE-DSH-P3.1）

日期：2026-10-14。Executor：Kimi。本轮零 DeepSeek API 调用、零费用；冻结区（Phase 0/1/1.6/2.1/2.2/2.3）未触碰。

## 交付项

| 项 | 状态 | 证据 |
|---|---|---|
| S1 算法定义 | PASS | docs/PHASE3_CEA_ALGORITHM.md（state/action/reward/update 正式定义；reward 来自反事实差值） |
| S2 Controller 架构 | PASS | src/causalevo/evolution/{controller,policy,bandit,reward,memory}.py；select_intervention 接口含 selected_action/confidence/policy_version |
| S3 三基线 | PASS | B0 random / B1 rule / B2 CEA-v0（disjoint LinUCB，纯 numpy，可序列化） |
| S4 离线演化仿真 | PASS | scripts/run_cea_simulation.py：60 episodes 严格时间序、评估窗不更新、EpisodeMemory 结构性防泄漏 |
| S5 评估协议 | PASS | docs/PHASE3_CEA_EVAL.md（top-1/成功率/累计奖励/regret/学习曲线/时间切分） |
| S6 消融 | PASS | A1 无历史 vs A2 有历史（历史无益，如实记录）；A3 普通奖励 vs A4 因果奖励（口径差异演示） |
| S7 结果产物 | PASS | results/phase3/cea/ 五件 + results/phase3/replay_sweep/（42 行完整奖励矩阵，容器实跑） |
| S8 测试 | PASS | **336 passed / 0 failed / 0 skipped**（300 回归 + 36 新增：bandit 8、policy 12、controller 9、仿真 7） |
| 文档 | PASS | docs/PHASE3_CEA_{ALGORITHM,EVAL,DESIGN,RESULTS}.md |

## 关键数字（评估窗）

B0 奖励 0.370 / regret 0.594；B1 0.964 / 0；B2 0.964 / 0（top-1=1.0）。消融：A2 历史无益（0.949 vs 0.964），A3 普通奖励虚高（1.0）仅作口径演示。

## 事故与修复

- sweep 首跑路径名含冒号+超长（WinError 123/267）→ run tag 短哈希化。
- Docker Desktop 双开导致 API 500 → wsl --shutdown 恢复（环境运维记录，非代码问题）。
- LinUCBPolicy 无 .alpha 属性（测试引用错误）→ 改指 .bandit.alpha。
- eval 标记名不一致（none vs eval-no-update）→ 统一。

## 停止

停在 Phase 3.1。status.json = READY_FOR_REVIEW，next_actor=GPT-Planner。未宣称自进化成功。
