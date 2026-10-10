# CausalEvo-DSH

黑盒 LLM Agent 受控进化实验平台（DeepSeek Harness + DeepSeek 官方 Flash API）。

- 研究范围与阶段边界：`docs/RESEARCH_SCOPE.md`
- 当前阶段：Phase 0 — 平台与缓存测量（`planner/latest_plan.md`，Plan CE-DSH-P0-R1）
- Harness 集成说明：`docs/HARNESS_INTEGRATION.md`
- Phase 0 审计：`docs/PHASE0_AUDIT.md`；结果：`docs/PHASE0_RESULTS.md`
- 执行协议：`planner/WORKFLOW.md`；机器状态：`status.json`

## 快速开始（Windows PowerShell）

```powershell
py -3.10 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.venv\Scripts\python.exe -m pytest tests/ -q                 # 离线测试，无需密钥
.venv\Scripts\python.exe benchmarks\cache_benchmark.py --dry-run   # 离线基准
# live（需要环境变量 DEEPSEEK_API_KEY，受预算门控）：
.venv\Scripts\python.exe benchmarks\cache_benchmark.py --live
```

Linux/WSL 同理（`python3.10 -m venv .venv`）。live 模式默认预算上限见
`configs/cache_benchmark.yaml`（`max_cny`），超预算即拒绝新请求并安全退出。
