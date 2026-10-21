# Executor Report — CE-DSH-P4-R1.7（测试兼容性 / 诊断工件 / 算法真实性审计 / 预注册提案）

日期：2026-10-21。Executor：Kimi。本轮**新增真实 DeepSeek 模型 API 调用 0 次、费用 ¥0**；未运行 `--live`；未查询余额；无任何真实实验。

计划：planner/latest_plan.md（CE-DSH-P4-R1.7）；审查：planner/reviews/CE-DSH-P4-R1_6-independent-review.md（R1.6 已验收，离线范围）。

## 1. Git 状态

- 起始 SHA：`b35e6dcc5c966b75df99d72b6a9621aed09528a1`（接管时工作区 clean；远端实际 HEAD 与预期基线一致）
- 最终 SHA / 远端 SHA / clean-clone 验证 SHA：见末节「Git 交付」

## 2. Task A：数字位数测试兼容性（PASS）

- **缺陷**：`test_digit_limit_literal_controlled_corrupt` 用 `hasattr + limit + 10`；`get_int_max_str_digits()` 在限制被禁用时返回 `0`，此时构造出无害的 10 位整数而非超限夹具。
- **修复**（tests/test_budget_proxy_r16.py）：抽出 `_extreme_int_literal(getter)`——limit>0 → `9*(limit+10)`；接口不存在或 limit==0 → 5000 位（解析后经 `_valid_amount` 的 float 转换溢出兜底，仍受控 corrupt）。
- **新增回归**：`test_digit_limit_zero_means_unlimited_falls_back_to_overflow`（注入式 getter，**不改全局解释器设置**；断言 0→5000 位、4300→4310 位、当前运行时选择为极端形态之一）。
- **保留断言**：代理构造不抛异常、corrupt+stopped、拒绝新请求、重启 fail-closed、账本字节不变——全部保留；正常金额重放不受影响。
- 结果：`pytest tests/test_budget_proxy_r16.py -q` → **8 passed**（原 7 + 新增 1）。

## 3. Task B：可审计脱敏直连诊断记录（PASS）

- 产物：`results/phase4/route_diagnostics/20261021.json`（本轮**未发起任何新探测**；仅整理既有证据）。
- 关键可复现性核查：原诊断所读 `sidecar_latest.log` 已轮转——诚实降级并修正：找到覆盖诊断窗口的轮转文件 `sidecar_2026-10-21_11-16-08.log`（SHA-256 `06b0c3f8f9612accbbb7bf22018389e70b72519b11219cc5e7d10934d9681682`，131116 字节），窗口 11:20–11:24 实测 **128 条连接、api.deepseek.com 0 条**（R1.6 报告的 109 为轮转前快照读数，结论不变；两处读数均已如实记录）。
- 工件含：时间戳与时区、mihomo Meta v1.19.20（`verge-mihomo -v` 实测）、mode=global、TUN 关闭、系统代理状态、直连 opener 与白名单上游、DNS/TCP/TLS 结果与证书身份、窗口/总数/匹配数、复现方法（grep 命令）、Sangfor aTrust 残余限制、零 HTTP/零调用/不构成授权声明。
- 未提交：原始日志文件（含无关连接历史）、任何凭据、完整环境变量转储。

## 4. Task C：算法真实性审计（核心结论）

产物：`docs/PHASE4_R1_7_ALGORITHM_FIDELITY.md`（逐行源码审计，全部结论附文件/函数/测试证据）。

- **C1 离线进化**：真实执行——`run_evolution.py::nsga3_evolve` 驱动真实 NSGA-III（支配排序 + Das-Dennis 参考方向 + ASF 归一化 + 小生境选择；pop 6 × 3 代），适应度来自容器世界**反事实重放测量**（非模型预测），多目标真实参与选择。**IMPLEMENTED_AND_TESTED**，但为 tape 模拟干预、小规模（基因型 144→表型 16）。
- **C2 Pareto 工件**：由 run_evolution 产生并写 train+test 适应度；独立 manifest 钉住 canonical SHA-256；adapter 加载前强制比对、每次读取复检。**IMPLEMENTED_AND_TESTED**。瑕疵如实记录：前沿 6 成员仅 4 唯一基因组（重复个体）；一个成员含 reserved 基因（无表型效果）。
- **C3 运行时**：**STATIC_ARTIFACT_ONLY**——冻结部署：失败证据→选前沿成员→派生干预文本；**不更新** genome/适应度/种群/前沿；无运行时演化闭环。
- **C4 递归自我改进**：**NOT_IMPLEMENTED（L4）**。L1 运行时修复重试 ✔；L2 策略更新仅离线模拟（部署侧 frozen-no-update）；L3 演化搜索仅离线；L4 不存在（无元演化/算子自适应/自我修改）。
- **C6 基线保真**：历史 B4=if/else 代理、B5=静态 bundle（名义与执行不符，已如实标注，历史文件不改）；R1.1+ 适配器仅有 fake-provider 离线 smoke。
- **C7 科学证据**：历史 312 行（¥0.715）：B0 0.808 / B1 0.923 / B2 0.885 / B3 0.827 / B4 0.846 / B5 0.885；B5 vs B0 p=0.344（ns）、B5 vs B1 p=0.727（ns，随机基线更高）；CI 跨 0。**算法优越性无证据，递归自我改进未实现**——两项均如实写明。

## 5. Task D：预注册实验提案（已撰写，未执行）

- 位置：`docs/PHASE4_R1_7_PILOT_PROPOSAL.md`。
- **判定：有条件 GO**——理由：历史 312 行未测试真实算法臂（B4/B5 为代理实现），真实冻结适配器臂从未 live 测试，存在新的可证伪公平比较；若结果为负，应先做运行时在线更新（L2）再谈 L3/L4。明确标注：该 pilot 验证冻结策略部署效果，不是 RSI 证据。
- 内容：H1（B5-v2 恢复率 > B1-random ≥ +0.10）+ H2 成本 ≤1.2×；26 任务 × 2 种子 × 4 臂配对；McNemar 精确检验 + task-level cluster bootstrap + Cohen's h + Holm；每 scope ≤8 请求、硬上限 ¥2.00；费用估算低/基准/高 = ¥0.35/¥0.50/¥1.00（来自历史实测 ¥0.715/312 行，标注假设）；fail-closed 停止规则；可复现 manifest；312 行历史数据隔离不可合并。
- **提案 ≠ 授权**；需用户显式预算授权 + Planner 批准。

## 6. 测试结果（实际命令与真实输出）

| 项 | 命令 | 结果 |
|---|---|---|
| r16（含新回归） | `pytest tests/test_budget_proxy_r16.py -q` | 8 passed |
| 预算四套件 | `pytest tests/test_budget_proxy{,_r14,_r15,_r16}.py -q` | 102 passed |
| 五关键套件 | credential/control/e2e/adapter/v2 | 50 passed |
| **全量** | `pytest tests/ -q` | **575 passed / 0 failed / 0 skipped** |
| clean-clone | `python scripts/clean_clone_check.py`（最终 SHA） | 见 Git 交付节 |

本轮无失败重试粉饰：唯一失败的初跑为 Task A 缺陷复现期（修复后全绿）；Docker 全程可用，无 NOT_VERIFIED。

## 7. 数据与安全

- 历史数据哈希：`calls.csv` `1961bdd8…`、`auditable_tasks.jsonl` `35b9e67a…`、sweep `15e2cb84…`（均未变）。
- 本轮 `results/`、`benchmarks/` diff：仅新增 `results/phase4/route_diagnostics/20261021.json`（脱敏工件）；无冻结内容修改。
- 密钥扫描：`git diff --cached | grep -cE "sk-[A-Za-z0-9]{32}"` = 0。
- 新增真实模型调用 0 次；费用 ¥0；新增测试不含真实 API 调用。

## 8. 费用与授权

真实 API 调用 0 次、费用 ¥0；未授权任何真实实验；预注册提案仅为文档。

## 9. 未解决问题

1. live readiness 仍为 **NOT_READY**（无预算授权）。
2. 冻结 Pareto 前沿含重复基因组（6 成员 4 唯一）+ reserved 基因成员——选择空间狭窄，已如实记录（不影响工件可验证性）。
3. Sangfor aTrust 底层路由残余限制（TLS 端到端认证已通过）。
4. Planner 未独立重跑本机测试套件；数字为 Executor 实际输出。
5. 若未来批准 pilot：须先重检 TUN/代理配置未变，再按提案前置条件执行。

## 10. Git 交付（最终 SHA / clean-clone / 同步）

（push 后实测填写。）

## 停止

停在 Phase 4 R1.7。未进入付费 pilot，未进入 Phase 5。`next_actor = GPT-Planner`。
