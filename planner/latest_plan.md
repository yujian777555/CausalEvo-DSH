# CE-DSH-P4-R1.11-FIX1 + R1.12 — Fix Audit Blockers, Then Run a Bounded Live Replication

Baseline: `4f60c4e400fe0f47bf822e9ded0d652be38e88e0`
Independent review: `planner/reviews/CE-DSH-P4-R1_11-independent-review.md`

## Authorization and hard budget boundary

The user explicitly requested on 2026-10-27: “快点进行实验吧”. Proceed with one new real DeepSeek replication after all gates pass. Because no new amount was specified, use the previous conservative ceiling as the new-run limit: **CNY 2.00 cumulative for this new run only**. Historical R1.9 spend (CNY 1.4633796936 including UNKNOWN bound) is historical and must not be altered or mixed into the new run.

- New-run warning line: CNY 1.80; cumulative hard stop: CNY 2.00.
- Count canary, all attempts, interruptions, resumes, settled charges and UNKNOWN reservation upper bounds. Never reset the cap by changing run IDs or restarting the proxy. If multiple ledgers are unavoidable, use a parent authorization ledger and reduce each new run's cap to the remaining amount.
- Unknown cost, corrupted ledger, ambiguous in-flight request, provider 5xx, SSE/transport failure or protocol error: stop all live activity; never retry the uncertain request.
- Do not query account balance. If a mandatory path cannot run without a balance query, stop before the first live request and report the blocker.
- No key in the agent container, argv, Git, logs or artifacts. No spending above CNY 2.00; no automatic top-up; no Phase 5.
- **R1.11-FIX1 and all pre-live gates must pass before the first new API request.** If any fail, no live call.

## Stage 1 — Mandatory R1.11-FIX1 (offline only)

1. Restore the three historical estimates from the immutable R1.10 artifact at commit `2bb9e5c3e6f9ac8c01e9f2529d4939459b055b1e`:
   - CEA-v2 vs B1: p=0.7462, stat=-0.038461538461538464, n_clusters=26, n_permutations=20000, seed=20261026.
   - CEA-v2 vs B5: p=0.62095, stat=-0.038461538461538464, n_clusters=26, n_permutations=20000, seed=20261026.
   - CEA-v2 vs B0: p=0.7268, stat=0.038461538461538464, n_clusters=26, n_permutations=20000, seed=20261026.
2. Put them in a stable immutable source with provenance. Never rely on reading the generated `sensitivity.json` as their sole source.
3. Strengthen tests to assert exact historical records and metadata; run the generator twice; prove byte-identical output and preservation after both runs.
4. Keep exact DP p-values unchanged: 0.75, 0.625, 0.7265625, 1.0. Update all manifest hashes.
5. Normalize `status.json`, preserving historical R1.10/R1.11 records. Distinguish code/data SHA from docs-only SHA and actual clean-clone-tested SHA. 631 prior test passes remain Executor-reported; GPT has not rerun local pytest.
6. Run focused and full tests. Run clean-clone on the exact FIX1 SHA. If any gate fails, stop without live calls.

## Stage 2 — Pre-register R1.12 before any API request

Commit `docs/PHASE4_R1_12_REPLICATION_PROTOCOL.md`, runner changes and tests **before the canary**.

### Scope and rows

- This is a **fresh-seed replication on the same 26-task microbenchmark suite**, not unseen-task generalization. R1.9 task IDs are reused; only seeds/run IDs change.
- Tasks: all 26 frozen tasks under `benchmarks/tasks/`; canonical manifest SHA-256 must remain `fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`.
- New seeds: `20261027`, `20261028`. Add an explicit CLI/config argument if needed; preserve the historical default seeds and all historical artifacts.
- Arms: B0-original, B1-random, B5-v1-frozen-pareto, and the online controller using R1.10 CEA-v2.1 incremental-fitness/no-op-feedback semantics. Preserve code-compatible arm identifiers if needed, but record algorithm/policy version unambiguously.
- Planned main data: 26 tasks × 2 seeds × 4 arms = 208 rows. Canary is excluded from efficacy analysis but counts against the same cumulative cap.
- New outputs go under a unique R1.12 run directory. Never overwrite or merge historical R1.9/R1.10/R1.11 data or ledgers.

### Frozen analysis

- Primary endpoint: binary `final_success`, fixed planned denominator; classify infrastructure/UNKNOWN outcomes explicitly and never silently drop them or reward infrastructure failures.
- Primary comparison: CEA-v2.1 online vs B1-random.
- Primary statistic: task-cluster paired mean difference, both seeds kept together; exact two-sided sign-flip test over 26 clusters plus 10,000-resample task-cluster bootstrap 95% CI.
- Secondary comparisons: CEA-v2.1 vs B5, CEA-v2.1 vs B0, B5 vs B1; Holm-correct secondary p-values.
- Practical improvement claim only if primary difference ≥ +0.10, exact cluster-aware p < 0.05, and 95% CI lower bound > 0. Otherwise say “no evidence of improvement.”
- Report success rates, paired differences, p-values/CIs, discordant task clusters, calls/tokens/cost/latency, online update counts and NSGA-III selection counters.
- 26 clusters may be underpowered. No unseen-task generalization or L4 RSI claim.

### Algorithm fidelity

- Run fake-provider end-to-end tests before live.
- Verify incremental attempt-2 cost/calls, no-op observation exactly once, and no learning from infrastructure/UNKNOWN outcomes.
- Record `nsga3_parent_selection_calls` and `nsga3_survivor_selection_calls` from live event logs. Claim NSGA-III selection only if the actual counters are positive. If both remain zero, report that; do not change parameters or rerun after seeing outcomes to force a call.
- Do not tune weights, mutation, intervention mapping, task selection or analysis based on new outcomes.

## Stage 3 — Live gates and run

1. After all code/tests/protocol are committed, verify remote HEAD and frozen hashes; run focused/full tests and clean-clone against the exact pre-live SHA.
2. Verify live authorization, secret isolation, provider allowlist/HTTPS, proxy auth, request validation, atomic reservation, resume/reconciliation and fail-closed behavior. No real key in agent space or argv.
3. Run one minimal canary first. Count all canary spend/UNKNOWN bound against the new CNY 2.00 cumulative cap. Continue only after authentication, usage accounting and ledger reconciliation pass.
4. Run the 208-row replication with the new seeds. Do not exceed CNY 1.80 warning / CNY 2.00 hard cap. If cumulative accounting cannot be enforced across canary/interruption/resume, do not start live.
5. No retry after unknown cost, no ledger resets, and no reconciliation that erases settled spend. If truncated, report actual coverage and stop; no top-up.

## Stage 4 — Analysis and final gate

- Add a separate R1.12 analysis script; do not alter historical R1.9 analysis semantics. Reject missing/duplicate task-seed-arm keys before analysis.
- Recompute outcomes and cluster-aware statistics deterministically from committed R1.12 rows.
- Reconcile every new ledger, including canary/interrupted/resumed runs; settled + UNKNOWN bound must remain ≤ CNY 2.00.
- Preserve Phase 0–3, historical 312 rows and R1.9's 208 rows byte-for-byte. Verify hashes, secret scan, status consistency and diff.
- Run full `pytest tests/ -q` and clean-clone against the **exact final origin/main SHA after the last commit**. No commits after the final gate; if any commit is made, rerun it.
- Report exact final SHA, actual API calls, settled spend, UNKNOWN bound, cumulative spend, row coverage, NSGA-III counts, statistics, test count and clean-clone output.

## Stop conditions

If Stage 1 fails, the protocol is not committed, the budget cannot be enforced, the secret/proxy gate fails, or canary accounting is uncertain, stop without any further live calls. No Phase 5.

## Required final response

1. Are all three historical estimates retained after two byte-identical regenerations?
2. Did exact-SHA clean-clone pass before live?
3. Actual new API calls and settled + UNKNOWN-bound spend?
4. Completed rows out of 208; are task/seed/arm keys complete and unique?
5. Exact live NSGA-III parent/survivor call counts?
6. Primary cluster-aware difference, exact p, 95% CI and Holm-adjusted secondary results?
7. Frozen historical data, full tests and final-SHA clean-clone status?

Next actor: Kimi-Executor.
