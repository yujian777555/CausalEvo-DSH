# CE-DSH-P4-R1.3 — Proxy Credential Isolation, Ledger Recovery & Run Scoping

Planner review base: be14f380433e6b08788e8dc47950a3a90c640b72

正式独立审查：planner/reviews/CE-DSH-P4-R1_2-independent-review.md

本轮必须修复 R1.2 独立审查中列出的全部 P0，并补齐 P1 回归测试。**新增 DeepSeek 模型 API 调用 = 0，新增付费预算 = ¥0。** 只允许 Fake Provider、离线重算和 Docker fake E2E。

## 0. 接管

- fetch origin/main，确认 HEAD。
- 阅读本计划、独立审查、status.json、Executor 报告。
- 保留 Phase 0–3 与 Phase 4 2026-10-14 的 312 行真实历史记录及 SHA；不得回填、重命名或重算覆盖历史原件。
- 本轮结束前不运行 --live，不做真实余额查询、不连接真实 DeepSeek。

## S1 / P0：密钥隔离

- run_phase4_pilot.py 不得把真实 DEEPSEEK_API_KEY 写进 live_pilot._API_KEY_HOLDER，再由 _current_key() 传给 Agent。
- 真实 key 只可用于宿主侧必要的 balance 查询和 Proxy trusted config；Agent 容器必须收到无权限 placeholder，建议通过明确的 proxy-mode 构造参数强制保证，而非依赖默认值。
- 对序列化给容器的完整 JSON、stdin payload、容器 env、trace、stdout/stderr、异常做 secret canary 测试：真实 canary key 在任何 Agent 可见位置都必须为 0 次；trusted Proxy upstream 收到正确的 key。
- 测试应调用实际 request builder/run path，不允许只断言 runner 对象属性。

## S2 / P0：Ledger 事件重放与预算恢复

- 在 BudgetProxy.__init__ 中重放 append-only ledger，按 request_id 校验合法状态转换并恢复：
  - _states；
  - 所有 SETTLED 的累计已知费用；
  - 每个评估 scope 的 request count；
  - 已知 in-flight reservation；
  - UNKNOWN/损坏/矛盾状态与全局停止条件。
- 任意 RESERVED/SENT 在启动恢复后转为保守 UNKNOWN；不确定费用时停止新请求。
- 人工 reconcile 必须有记录和显式 scope；不能因解除 UNKNOWN 而清零历史 known cost 或 per-scope counts。
- 处理重复日志事件、截断行、非法 JSON、负数费用、同 request_id 冲突。账本不能被完整、可信地恢复时 fail-closed。
- 在 reservation/SENT 发送前持久化；评估 flush/fsync 与原子写语义。测试重启/模拟崩溃后预算不得归零。
- 必测：成功结算 N 次→关闭/重启→恢复相同累计费用和请求数；再请求超限时 0 次到达 upstream。

## S3 / P0：唯一评估 scope 与控制 ACK 协议

- 不能再只使用 spec.task_id 作为 per-task cap key。定义稳定且唯一的 evaluation scope，至少含 experiment_run_id/task_id/seed/arm；attempt 另有 attempt_id，但同一逻辑评估的所有 attempts 应按预注册的预算语义归属。
- 修改 runner 调用协议，让每条逻辑评估在第一个 Provider 请求前设定 scope；禁止把 6 arms × 2 seeds 混在同一个 task bucket。
- 控制消息包含 generation/request_id。宿主先删除旧 ACK，再原子替换发布新控制消息；Proxy ACK 必须回显同一 generation。禁止通过仅比较 task_id 判断消息是否新鲜。
- 控制通道超时、generation 不匹配、账本共享挂载不可用时，拒绝启动 Agent。
- 测试连续两次相同 task_id、相同 task 不同 arm/seed、快速 A→B→A、重复 retry、延迟 ACK 和并发控制。
- 明确若代理只支持串行单任务，运行器必须强制串行并用锁保证 attribution；若支持并发，必须按每个请求携带受信 scope token，而非全局 mutable _current_task。

## S4 / P0：Proxy ingress 认证与网络隔离

- Proxy 连接 internal ceval-net 与 egress network 时，不能无条件在所有接口暴露一个未鉴权的转发器。
- 在 Agent→Proxy 方向添加独立的代理客户端认证（不能复用或泄露上游 API key），或实现等价且测试证明的网络级隔离。实际 DSH SDK 必须能够携带此认证；若不能，不得宣称安全接入。
- 证明 default-bridge sibling container 无法访问 Proxy 或不能通过认证。不能只证明端口未发布到宿主机。
- Proxy 只能连接预先允许的 HTTPS 上游主机（live 为 api.deepseek.com），不能让 Agent 或不可信环境变量指定任意 URL、内部地址或协议。
- 限制 HTTP 方法、路径、body size、model、max_tokens/max_completion_tokens 和输入规模；拒绝超出 worst-case reservation 配置的请求，拒绝必须发生在 upstream socket 发送之前。
- 固定允许模型为 deepseek-flash，除非另有冻结协议批准。校验实际 request JSON 与预留的 worst-case prompt/output tokens 一致；若无法可靠界定输入规模，保守拒绝。
- 所有入站拒绝、鉴权失败、上游失败、未知 usage 都写审计 ledger；不得记录 key 或完整 prompt。

## S5 / P1：修复控制与输出目录边界

- 修复 run_phase4_pilot.py 中 out_dir 在赋值前被 --out 真分支读取的问题：先解析 out_dir/run_dir，再启动 Proxy。
- Proxy cap E2E 加入 FakeProvider 真实接收请求计数器，不能用 Proxy 自己的 SENT 行替代上游计数。
- 新增 fake tests 验证请求大小/model/output cap、proxy ingress auth、default bridge sibling 拒绝、未知费用锁定、重启恢复、重复 scope。
- Clean clone 应验证所测试 HEAD 与 origin/main 或目标 SHA 完全一致；保留 no-raw-tasks 断言。

## S6 / P1：算法 smoke 测试准确定位

- 在独立 manifest 中冻结 pareto_front.json 与训练 sweep 输入的 SHA-256；适配器加载前必须和 expected hash 比较，不能仅计算当前文件 hash 后自证。
- 对 CEA-v1 建立多种 fake failure fixtures：invalid/verification、no-edit/read-first、edited-but-failing/tool-validation、infra/unknown-cost no-retry。实际运行驱动必须观察到各分支及不同选中 genome；edited 等状态不得硬编码，应由 workspace/trace 计算。
- 对 CEA-v0 同样记录固定 snapshot hash、action、policy_version 和 no-update 约束。
- run_phase4_v2_offline.py 的结果标为 adapter_integration_smoke，不能宣称算法泛化、真实 Agent 提升或 NSGA-III 优越性。
- 真实模型 live 评估仍需单独的预注册与新授权，不属于本轮。

## S7：状态、测试与证据

- 更新 status.json：清理过期 blockers，保留历史 R1.1/R1.2 审查记录，将当前未关闭问题列入当前 blockers。
- 全量运行可执行测试，并分别报告 unit/integration/Docker E2E/clean clone/secret isolation/ledger recovery/scope attribution。
- 任何 Docker 测试若因镜像/daemon 未启动而 skip，必须标记 NOT_VERIFIED，不能归为 PASS。
- 更新 planner/executor_report.md 和版本化结果；不修改历史真实数据。
- 新增 DeepSeek model API calls = 0，费用 ¥0。

## Gate 与停止

Gate A：Agent 请求中不含真实 API key。
Gate B：重启后 known spend 与 per-scope request counts 完整恢复。
Gate C：相同 task 重复设置不会 ACK 超时；不同 arm/seed 预算独立。
Gate D：未经认证的 bridge sibling 无法使用 Proxy。
Gate E：请求 model/body/token 超限在发送前拒绝。
Gate F：Fake Provider 端到端实际计数验证 cap-before-send。
Gate G：CEA-v0/v1 多种离线分支被真实驱动触发；SHA 由独立 manifest 钉住。
Gate H：clean clone/历史数据复算一致，冻结数据不变。
Gate I：本轮新增真实模型 API 调用 0、费用 ¥0。

所有 P0 Gate 通过后，设置 phase_status=READY_FOR_REVIEW、next_actor=GPT-Planner；任何 P0 未通过则 BLOCKED。推送 main、核验 HEAD 与工作区 clean 后立即停止，等待 Planner 审查。不得进入付费 pilot 或 Phase 5。
