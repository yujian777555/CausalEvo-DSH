# CE-DSH-P4-R1.2 — Fresh Clone Reproducibility & Provider Proxy Integration

Planner 审核 SHA：`9c7148eb34020c50295a0bda52cef0647df9702b`
正式 review：`planner/reviews/CE-DSH-P4-R1_1-independent-review.md`
**本轮不准任何收费/模型 API 调用，预算 ¥0；也不可重新跑旧数据覆盖负面结果。**

## S0 先确认代码与证据

Fetch origin/main；阅读 Review，检查历史冻结 hashes。旧 312 条实验不改动，原始来源 SHA 保留；只在新 audit 产物/独立模块修复。

## S1 — P0 干净克隆可复算

- 为 `auditable_tasks.jsonl` 实现专用 reader：跳过并验证开头两行 `#` 元数据，解析并独立验证 312 行 row_sha16、字段、唯一 `(task_id,arm,seed)`、6x52、成本和试验摘要。源原始 `tasks.jsonl` 不应是复算必需品。
- 修改 `scripts/analyze_phase4.py`、`recompute_phase4_stats.py` 和相关 tests/CI，让默认任务为只读 auditable projection；**保留**读取 original 并对照生成投影的独立可选 local-only 命令，缺失原始数据时不能伪称恢复成功。
- 新建最小 fresh-clone 冒烟检查：在工作树暂时无法找到 `tasks.jsonl` 时所有统计/审计测试应通过；不能依赖已忽略的 scratch raw logs；测试不要因为代码依赖固定 Windows 路径而虚假通过。
- 输出 versioned audit 对账文件，不修改 2026-10-14 原摘要。Task cluster bootstrap 与 McNemar/pairs 独立再生，与 R1.1 结果一致。

## S2 — P0 Proxy 正式连入 ContainerHarnessRunner

- 直接源码更新 `scripts/run_phase4_pilot.py` 的 live make_runner：显式创建并持有 `BudgetProxy` 生命周期，将 Harness base_url 指向 Docker 容器可访问的受控 proxy 地址；proxy 转发到用户批准的 DeepSeek 官方主机必须 DIRECT。不能保留 `provider_endpoint=None` 作为任何实际 live 路径的 fallback。
- 明确代理宿主与 Docker 的网络拓扑：`127.0.0.1` 只对所在网络命名空间可见；设可达私有绑定地址 + 容器可验证路由，同时配置访问控制及防止未经授权容器任意访问 proxy；Docker 不可任意公网出口。
- 完整保留必要上游请求头（特别是 `Authorization`）但不得记录密钥；透传应当只允许经过验证的 Provider 主机，删除敏感日志。测试必须使用拒绝无鉴权的假服务端，证明不会变成真实 401。
- 每个 task_id/attempt/request_id 应由可信运行端生成并自动进入 proxy 账本；不要依赖 SDK 未发送的 `X-Task-Id`。若 SDK 无法注入头，用 proxy 分配受信 task-scoped session endpoint/token，分别验证不能串账。
- 完整 live 链端到端使用 FAKE provider：Docker Harness → proxy → fake SSE 多轮调用 → judge；验证真实的 cap-before-send、网络 ACL、安全停止、partial ledger。**不调用 DeepSeek**。

## S3 — P0 并发/异常/预留原子性

- 在 `_check` 时实际登记 `in_flight_reserved_cost_cny` 并在持久日志中写入预留 BEFORE forward；对同一时刻不同请求的 projected cost 必须累加 in-flight reservation。完成时单次 settle/release；疑似计费仍保留未知额并阻止进一步发送。
- 引入 atomic request state（reserved/sent/settled/unknown）；支持进程恢复时对未完成状态 fail closed；不可把只在结算时持久化称为 crash-safe。
- 验证并发 2–10 个 **不同 body**、全局 cap 仅够一个时后续全部 pre-send rejected；重复 request_id 与不同 request_id 同 usage 的情况也覆盖。HTTP 500/401/EOF、stream truncation、lack of usage 都全局停机，未知支出不可归零。
- 明确 `stream:true/false` 支持范围、SSE response 连续性与 usage 包含约束；代理必须以实际 DSH/OpenAI-compatible traffic 的请求形式离线测试，不能只测简化 FakeProvider 的无鉴权 happy path。

## S4 — P1 Algorithm adapter 真正接入评估调度（离线）

- 为 `CausalPolicyAdapter.cea_v0` / `cea_v1` 设计新版本独立臂和冻结 policy manifest；runtime 在失败后从真实 controller/genome adapter 选可执行 intervention。旧 B4/B5 数据不可改名换数字或回填。
- CEA-v1 如声称 failure-conditioned，就必须采用预先冻结的 failure-context/目标/预算约束选择不同 Pareto candidates；如果不能，客观描述为 single frozen evolved genome，不得把静态选择称为状态自适应。
- 强制校验 expected_sha256（从独立冻结 manifest）而非只计算源 hash；显式选择 genome_id / phenotype_id / training provenance，避免 silent max over train_fitness 和重复 phenotype 误导。
- 包括至少 2 种失败情境能触发不同策略（若方法设计确实要求），并用 fake Agent 驱动而不止 unittest 模拟适配器调用。

## S5 — P1 直连与 CI 真验证

- 删除 `tests/test_direct_connect.py` 的 `or True` 占位断言，新增可在 Linux/Windows 上执行的行为级 offline mock。TUN 层直连仍由用户本地代理客户端路由/连接日志确认；未确认标 `DIRECT_ROUTE_UNVERIFIED`，不可绕过外部审批。
- 使用真正干净 git clone / isolated venv 执行 pytest、数据复算、fake container-proxy e2e；分别记录无 Docker 时的跳过原因和有 Docker 时的实测结果。不能因为本机 raw tasks 文件仍存在就声称 fresh clone PASS。

## 验收与交付

Gate A：仓库单独 checkout，无 tasks.jsonl 时 312 auditable 行完整重算成功。
Gate B：live Runner 已实际连接可达且安全的 proxy；需要至少 Docker 假服务端从发请求到 ledger 的 E2E。
Gate C：并发请求下不超预算，失败/异常/崩溃预留 fail closed；认证头正确透传。
Gate D：冻结 NSGA-III 与 LinUCB 通过新 adapter 在新实验调度中实际被调用，且与历史代理臂分离。
Gate E：全量历史测试和新测试可信；Phase0–3/2026-10-14 真实结果完全不变。
Gate F：新 DeepSeek calls=0、付费预算 ¥0、工作区 clean、push main 并附 SHA。

如 Gate B 或 C 无法在不付费下完成，标 `BLOCKED` 并维持全部 live entrypoints 为关闭状态。更新 `status.json` 和 `planner/executor_report.md`，完成后 `READY_FOR_REVIEW`，等待 Planner 复审；不要自动进入 SWE-bench/Phase5。