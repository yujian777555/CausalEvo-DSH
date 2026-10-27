# CE-DSH-P4-R1.12 — Fresh-Seed Same-Suite Replication Protocol

**Status:** preregistered before any R1.12 live request.  
**Authorization:** user requested a new experiment on 2026-10-27; new-run cumulative hard cap CNY 2.00.  
**Scope:** same-suite fresh-seed replication, not unseen-task generalization.

## 1. Research question

Does the current CEA-v2.1 online evolutionary controller improve final task success over random intervention selection and a frozen Pareto policy on fresh seeds, using incremental-fitness and explicit no-op feedback semantics?

## 2. Frozen benchmark and seeds

- Benchmark: all 26 tasks under `benchmarks/tasks/`.
- Canonical benchmark manifest SHA-256: `fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`.
- New seeds: `20261027`, `20261028`.
- Arms: B0-original, B1-random, B5-v1-frozen-pareto, and the online controller using R1.10 CEA-v2.1 semantics.
- Planned main rows: 26 × 2 × 4 = 208. Canary rows are excluded from efficacy analysis but included in the cumulative spend cap.
- R1.9 task IDs are reused; only seeds/run IDs are new. Conclusions are limited to replication on this fixed task suite.

## 3. Endpoint and estimand

- Primary endpoint: binary `final_success`, fixed denominator. Infrastructure and UNKNOWN outcomes must be separately classified; do not silently drop them or use them as behavioral rewards.
- Primary estimand: mean task-level paired difference in final success, CEA-v2.1 minus B1-random. Average paired differences over both seeds within each task, then average equally over the 26 task clusters.

## 4. Statistical plan

- Primary test: exact two-sided sign-flip test on 26 task-cluster mean differences, keeping both seeds together; enumerate the exact distribution with dynamic programming.
- Interval: task-cluster bootstrap, 10,000 resamples, 95% percentile CI; resample task IDs and keep both seeds together.
- Secondary comparisons: CEA-v2.1 vs B5-v1, CEA-v2.1 vs B0, and B5-v1 vs B1. Apply Holm correction to secondary p-values.
- Practical success criterion: primary difference ≥ +0.10, exact cluster-aware p < 0.05, and bootstrap 95% CI lower bound > 0. Otherwise conclude no evidence of improvement.
- Report task-cluster discordance, arm success rates, request/token/cost/latency summaries, and online-evolution telemetry. If fewer than 8 task clusters are discordant on the primary comparison, explicitly mark the study underpowered/exploratory.
- This is a 26-cluster replication, not an unseen-task generalization study or L4 RSI test.

## 5. Algorithm fidelity

- The controller must use the R1.10 incremental attempt-2 cost/call fitness contract.
- A selected no-op is observed exactly once with zero incremental cost/calls; infrastructure and UNKNOWN outcomes never become behavioral reward.
- Record `policy_version`, `population_version`, selected genome, selection reason, lineage, `nsga3_parent_selection_calls`, and `nsga3_survivor_selection_calls`.
- Claim NSGA-III selection was exercised only if live event counters show a positive call count. Do not change parameters after looking at outcomes.

## 6. Budget and stopping

- Cumulative hard cap for the entire new R1.12 effort: CNY 2.00, including canary, all live requests, interrupted attempts, resumes, settled charges and UNKNOWN reservation upper bounds.
- Warning line: CNY 1.80. Never reset or split the cap across run IDs. If multiple ledgers are unavoidable, aggregate them in a parent ledger and reduce each subsequent run's available cap to the remaining amount.
- Per-scope request cap: 8.
- On UNKNOWN cost, malformed ledger, ambiguous in-flight request, provider 5xx, SSE/transport failure or protocol error: stop all live activity, preserve artifacts and do not retry the uncertain request.
- No balance queries, no automatic top-up, no further live run after the cap is reached.
- If cumulative budget enforcement cannot be demonstrated before the canary, do not send any live request.

## 7. Reproducibility and data integrity

- Freeze this protocol and its hash before the first live call.
- New outputs use a unique R1.12 run directory and new ledger. Never overwrite or merge historical R1.9/R1.10/R1.11 artifacts.
- Validate all task/seed/arm keys and reject duplicates or missing rows before analysis.
- Analysis script and output hashes go in the R1.12 manifest. Analysis must be deterministic.
- Preserve Phase 0–3 data, the historical 312 rows, and R1.9's 208 rows byte-for-byte.
- Final full tests and clean-clone must pass at the exact final origin/main SHA; no commits after the final gate.

## 8. Interpretation limits

A positive result supports only a same-suite fresh-seed replication under the tested model, prompts, budget and 26 task clusters. It does not establish generalization to unseen tasks, superiority on broader Agent tasks, or recursive self-improvement at L4.
