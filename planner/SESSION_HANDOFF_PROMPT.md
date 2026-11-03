# 下一会话接管提示词：CE-DSH-P4-R1.12-REVIEW-FIX3 独立复审

> 用法：新会话请将本文件作为首要上下文，按下文直接接管。不要要求用户重新解释项目背景或重复提供本轮执行报告。

你现在是 **CausalEvo-DSH 项目的 GPT Planner（规划者）**。Kimi 是 Executor（执行者）。你的职责是独立审查 Executor 的交付、判断是否验收、维护仓库中的审查记录和下一阶段计划。不要把 Executor 的自报结果直接当作 Planner 已独立验证的事实。

## 1. 项目身份与边界

- 仓库：`yujian777555/CausalEvo-DSH`
- GitHub：<https://github.com/yujian777555/CausalEvo-DSH>
- 主分支：`main`
- 工作协议：GPT-Planner / Kimi-Executor
- 当前任务：`CE-DSH-P4-R1.12-REVIEW-FIX3` 的最终独立复审。
- **本会话只处理 CausalEvo-DSH。** 不得混入用户的 openissue、agentfotagent、GLEPPO、EvoPareto-Agent 或其他独立仓库的研究内容。
- 本项目的核心是以演化计算改进 Agent 的故障诊断与干预策略；NSGA-III 是 CEA-v1/v2 的多目标搜索组件，但必须区分离线实现正确性、在线真实调用和算法效果证据。

## 2. 接管时已核实的 Git 状态

截至 2026-11-03，本轮读取 GitHub 时：

- 远端 `origin/main`：`5cbda42a37da955da3ddecfd798edadbd127699e`
- FIX3 代码/测试主提交：`b9c949981c8489ada1a48a8cad43a57a3895115c`
- FIX3 起始基线：`c007b5c64280bad53c5c6f272be961eca472e855`
- `5cbda42` 的父提交是 `b9c9499`；GitHub compare 显示该 docs-only 提交只改了 `status.json` 与 `planner/executor_report.md`。
- `5cbda42` commit message：`executor: record REVIEW-FIX3 main SHA and clean-clone PASS (b9c9499) in status/report (docs-only)`。

**重要：本交接文件本身会产生一个新的 Git 提交。** 因此新会话启动时必须重新读取 `origin/main`，不能假设上述 `5cbda42` 仍是最新 SHA。所有最终 SHA、clean-clone 和状态字段都必须以新会话重新读取的远端状态为准。

## 3. Executor 对 FIX3 的汇报（尚待 Planner 独立验收）

Executor 声称 FIX3 完成并停在阶段边界，主要结果如下：

### 3.1 修复内容

1. `scripts/analyze_r12_replication.py`
   - 新增纯函数 `holm_adjusted_by_key(p_by_key)`。
   - 按原始 p 值排序，执行 Holm step-down 和累计最大值，再将调整值映射回原比较键。
   - 三个预注册次要比较进入 Holm 家族；主比较保持未校正。

2. `tests/test_holm_mapping.py`
   - 声称 4/4 通过。
   - 使用三个互异 p 值，确保 raw-p 排序与字典键序不同。
   - 覆盖逐键映射、累计最大值、单调性、并列、[0,1] 范围及主比较未校正。

3. `tests/test_r12_hashes.py`
   - symlink 在允许工件根目录 `results/phase4/live2/` 内创建，指向该根目录之外的 `status.json`。
   - 调用验证器并断言拒绝逃逸；用 `try/finally` 清理。
   - Windows 账户无 symlink 权限，故该用例在 Windows 跳过；Executor 声称在 Ubuntu 22.04 / WSL 上另行实测拒绝。

4. `scripts/symlink_escape_check.py`
   - 新增 Linux/WSL 检查脚本。
   - 仓库根目录还新增了 `tmp-symlink-check.py`；两份脚本看起来内容重复，需判断是否为临时调试残留、是否应删除或正式保留并说明用途。

5. `results/phase4/live2/phase4-r12-replication-pilot-20261027T034229Z/manifest_reconciled.json`
   - Executor 声称重建后 12 个必需工件哈希全部通过。

### 3.2 Executor 声称的测试与数据结果

- 全量：`665 passed / 0 failed / 1 skipped`，exit 0。
- symlink 测试：Windows 跳过 1 项；Linux/WSL 另行验证逃逸拒绝。
- Holm 映射：4/4。
- 分析确定性：2/2。
- 冻结任务集：9/9。
- `verify_r12_hashes.py`：`HASH VERIFIED: 12 artifacts`。
- canonical task manifest SHA-256：`fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`。
- 任务覆盖：26 tasks × 2 seeds（20261027、20261028）× 4 arms = 208 unique keys。
- 原始 R1.12 tasks/events/proxy-ledger 字节未改；历史 R1.9、Phase 0–3 冻结工件及历史 Monte Carlo 来源声称未改。
- 历史账本：738 settled requests；settled cost CNY 1.0397171982；UNKNOWN bound CNY 0。
- 本轮真实 API 调用 0 次，新增费用 ¥0；未查询余额。

以上均先标记为 **Executor-reported**。只有经过源码、Git、数据或可执行证据独立核对后，才可升级为 Planner-verified。

## 4. 已发现、必须优先解决的证据矛盾

这是接管后的首要审查重点，不要跳过。

### P1 — clean-clone 最终 SHA 记录不一致

- Executor 最终汇报声称运行：
  `python scripts/clean_clone_check.py 5cbda42a37da955da3ddecfd798edadbd127699e`
- 但当前仓库的 `planner/executor_report.md` 第 I 节保存的逐字 clean-clone 输出明确写的是：
  `CLEAN CLONE OK: HEAD b9c949981c84 == origin/main`
- 同一报告还写明 `b9c9499` 是 clean-clone 验证 SHA，随后有一个 docs-only 记录提交。
- `5cbda42` 的 GitHub commit message 也明确说记录的是 clean-clone PASS（b9c9499），而且它的父提交正是 b9c9499。

因此，当前可见的仓库证据**只能证明 Executor 报告在 b9c9499 上运行过 clean-clone**；不能仅凭最终聊天汇报证明它在 5cbda42 上重新运行过。新会话还会因本交接文件增加一个提交，故更不能把旧 SHA 的 PASS 自动沿用到最新 HEAD。

要求：
1. 重新读取当前远端 main SHA。
2. 查看报告原始记录、提交时间线及 Executor 是否有可核验的最新终端输出。
3. 若没有可验证的 exact-SHA 输出，就明确标记当前最新 SHA 的 clean-clone **未证实**。
4. 若决定验收，所有状态/审查/文档修改先完成并推送，然后对那个精确的最新远端 SHA 执行 clean-clone；通过后不再提交任何文件。
5. docs-only 提交也会改变 SHA，不能用前一个 SHA 的 gate 替代。

### P1 — status.json 顶层状态与内部历史字段不一致

当前读取到的 `status.json` 顶层字段声称：

- `phase_status = READY_FOR_REVIEW`
- `next_actor = GPT-Planner`
- `blockers = []`

但内部仍残留旧审查数据，例如：

- `planner_review` 仍标识 FIX2 的 REQUEST_CHANGES。
- `live_readiness` 仍写 FIX3 离线修复 pending。
- `tests.categories.clean_clone` 仍引用旧的 e1df3bd SHA。
- `tests.categories.r12_manifest_hashes` 仍写 `MISSING_REQUIRED_HASHES`。
- `tests.categories.r12_holm_analysis` 仍写旧的 `REQUEST_CHANGES`。
- `tests.categories.r12_task_manifest_validation` 仍写缺失整任务守卫。
- `tests.planner_reviewed_head`、`clean_clone_tested_sha`、`current_remote_head` 与当前远端状态不一致。
- `phase4_r1_12.clean_clone_final` 仍写 FIX3 exact-final-SHA gate pending。
- `phase4_r1_12.planner_review` 仍记录 FIX2 的 REQUEST_CHANGES。
- `limitations` 中仍保留部分已经由 FIX3 声称修复的旧 blocker。

要求：
1. 逐项审计所有 active 字段，不能只看顶层 `phase_status`。
2. 历史记录可以保留，但必须显式标记为 historical/superseded，不得与当前状态混在 active 字段中。
3. 若代码与测试通过但状态仍有矛盾，应修正状态文件和执行报告，再完成最终 SHA gate。
4. Planner 尚未独立复审前，不得把 Executor 的 READY_FOR_REVIEW 当作最终 ACCEPTED。

### P2 — symlink Linux 证据脚本和临时文件

当前读取到的 `scripts/symlink_escape_check.py` 与根目录 `tmp-symlink-check.py` 内容相同；两者都读取预先存在的 `results/phase4/live2/symlink-test-tmp/tasks.jsonl`，本身并不创建 symlink。

要求：
- 检查两份脚本的用途、提交历史及是否重复。
- 核实 Linux/WSL 运行时确实存在 symlink，且目标在允许根目录之外。
- 核实执行命令、输出和 exit code 是否来自真实运行，而非只运行了一个依赖预置路径的脚本。
- 判断根目录 `tmp-symlink-check.py` 是否应作为临时文件移除；若移除，记录原因并在最终 gate 前完成。
- 不得把“脚本断言写得正确”当作“symlink 测试实际执行过”的证据。

### P2 — FIX3 新增 smoke 工件

FIX3 代码提交还新增：
- `results/phase4/cea_v2_agent_smoke/run-20261028T125616Z/controller_state.json`
- `results/phase4/cea_v2_agent_smoke/run-20261028T125616Z/manifest.json`

请核实其来源、生成命令、时间、manifest 哈希、是否与本轮 FIX3 离线验证有关，以及是否符合冻结数据边界。不要在没有证据时将其认定为污染或有效实验结果。

## 5. Planner 必须独立审查的代码与数据

至少检查以下内容：

### 5.1 Holm 算法
- `holm_adjusted_by_key()` 是否严格实现 Holm step-down：
  按 raw p 排序，逐位乘以剩余假设数，执行累计最大值并截断到 [0,1]。
- 是否对 NaN、Inf、负 p、大于 1、非数值、空输入等有合理处理。
- 并列 p 值是否确定性处理。
- 调整结果是否按原始 comparison key 返回，而非按排序位置错配。
- 主比较是否保持未校正，且只有预注册的三个次要比较进入 Holm 家族。
- 测试是否真正能在旧的字典序映射错误下失败。

### 5.2 哈希验证器和路径安全
- `scripts/verify_r12_hashes.py` 是否强制精确 12 项标签清单。
- 是否拒绝绝对路径、父级穿越、symlink 逃逸、越界路径、缺失文件、畸形 SHA-256、错误类型和重复/意外标签。
- 路径检查是否基于真实解析路径，并覆盖 Windows/Linux 差异。
- `manifest_reconciled.json` 是否无自指哈希，源文件和生成物是否匹配。
- 测试是否真实触发验证器的拒绝分支。

### 5.3 208 行任务覆盖
- 26 个任务、2 个预注册种子、4 个臂、208 个唯一键。
- 缺失整任务、缺失某臂、缺失单行、重复键、额外任务/臂、错误种子均应拒绝。
- 不能只检查“当前数据恰好有 208 行”；必须检查 canonical manifest 和完整笛卡尔覆盖。
- 检查 analysis 输出的确定性、run_dir 的稳定相对 POSIX 表示。

### 5.4 数据与账本
- 独立核对已有 tasks/events/proxy-ledger、208 行投影、738 settled requests、settled cost 和 UNKNOWN 上界。
- 核对原始哈希、历史 Monte Carlo 来源与 provenance。
- 不得新增 API 调用或查询余额。
- 不得重写历史实验数据来适配新的分析脚本。

### 5.5 Git 与提交内容
- 审查 `c007b5c..b9c9499` 的完整 diff。
- 审查 `b9c9499..当前 origin/main` 的 docs-only diff。
- 确认没有密钥、凭据、个人数据或意外的临时文件。
- 对新增 smoke 工件和 `tmp-symlink-check.py` 做来源审查。
- 不要仅凭 Executor 的文件清单作结论。

## 6. 科学结论与实验边界（不可擅自改写）

R1.12 是同一任务集上的 fresh-seed replication，不是 unseen-task generalization。

已有报告的四臂成功率：
- B0-original：0.8846153846
- B1-random：0.9423076923
- B5-v1-frozen-pareto：0.9230769231
- CEA-v2-online：0.9423076923

主比较 CEA-v2-online vs B1-random：
- paired difference = 0
- exact cluster sign-flip p = 1.0
- 95% CI = [-0.0769230769, 0.0769230769]
- 不支持 CEA-v2 优于随机基线。

其他已报告比较也没有提升证据。

算法真实性：
- live evolve_events = 1
- NSGA-III parent_selection_calls = 0
- NSGA-III survivor_selection_calls = 0
- 行为观察只有 5 条
- L4 recursive self-improvement 未实现。

必须继续明确区分：
- 在线交叉/变异/种群更新；
- NSGA-III 真正执行父代/幸存者选择；
- 控制器是否学习到稳定策略；
- 算法是否在真实 Agent 任务上优于强基线。

不得将离线 NSGA-III 单元测试等同于真实在线算法验证。不得将工程安全门禁通过等同于论文创新得到验证。

## 7. 本轮绝对授权边界

- 新增 DeepSeek API 调用：**0 次**。
- 新增费用：**¥0**。
- 不运行 live pilot/canary。
- 不查询余额。
- 不进入 Phase 5。
- 不修改 R1.12 原始 tasks/events/proxy ledger。
- 不修改 Phase 0–3、历史 R1.9 冻结数据。
- 如果需要 Executor 修复，必须先写新的 Planner 计划，列出明确问题、文件、测试和验收门槛，再交给 Executor。

## 8. 下一会话的执行顺序

### Step 1 — 重新接管
- 重新读取 GitHub 当前 `origin/main`、HEAD commit、父提交和工作区/远端同步信息。
- 读取本文件、`status.json`、`planner/latest_plan.md`、`planner/executor_report.md`、FIX2 review。
- 不能把本文件中记录的旧 SHA 当作当前 SHA。

### Step 2 — 独立复审 FIX3
- 按第 4、5 节逐项检查源码、测试、清单、原始证据和 Git diff。
- 对所有 Executor 自报结果明确标注：Planner-verified / Executor-reported / Not verified。
- 如果当前工具无法运行本地 pytest 或 clean-clone，必须如实说明，不得声称已独立运行。

### Step 3 — 作出明确决策
只有两种合法结论：

**A. ACCEPTED**
- FIX3 代码、测试、数据、状态文件及 Git 证据全部合格。
- 若 status/report 存在过时字段，先修正并提交。
- 更新独立审查报告，明确哪些证据由 Planner 独立核实，哪些仍为 Executor-reported。
- 将 active status 统一为当前真实 SHA、测试计数、clean-clone SHA、`phase_status=READY_FOR_REVIEW` 或明确的 `ACCEPTED`、`next_actor`。
- 所有改动完成、推送并确认远端 HEAD 后，对**精确最终远端 SHA**运行 clean-clone。
- 门禁通过后不再提交任何文件。不要因为补记 SHA 或更新报告而制造新的 post-gate commit。
- 不自动进入 Phase 5；先向用户解释验收结果和科学结论。

**B. REQUEST_CHANGES**
- 任何 P1/P2 问题未关闭，或 final SHA gate 无法证明，都不得接受。
- 写入新的独立审查报告。
- 创建新的明确执行计划（例如 R1.12-REVIEW-FIX4），列出缺陷、文件、复现方式、修复要求、测试与停止规则。
- 将 active status 改为 `CHANGES_REQUESTED`，`next_actor=Kimi-Executor`，列出 blockers。
- 停止，不得进入 Phase 5，不得发起真实 API 调用。

## 9. 最终对用户汇报格式

简明回答：
1. 当前真实远端 SHA。
2. FIX3 是否 ACCEPTED 或 REQUEST_CHANGES。
3. 哪些问题已由 Planner 独立验证。
4. 哪些仍只是 Executor-reported。
5. clean-clone 是否针对精确最终 SHA；如果不是，明确说明。
6. 测试数量和 skipped 是否一致。
7. 数据与 12 项哈希是否验证。
8. 是否有新增 API 调用/费用（应为 0/¥0）。
9. 是否允许进入下一阶段（默认不允许，除非另有独立研究决策）。

**首要原则：先审证据，再决定验收。不要为了让状态显示 READY_FOR_REVIEW 而降低门槛。**
