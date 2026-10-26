# CE-DSH-P4-R1.10 — GPT Planner Independent Review

- Repository: \`yujian777555/CausalEvo-DSH\`
- Reviewed final HEAD: \`2bb9e5c3e6f9ac8c01e9f2529d4939459b055b1e\`
- R1.10 code/data commit: \`5d5777c80713356e2c0e2049e94e8499f8dc16dd\`
- Current HEAD is a docs/status-only follow-up to the code/data commit; the Executor reports clean-clone validation at 5d5777c, not at 2bb9e5c.
- Review method: direct GitHub artifact/source inspection and independent recomputation from committed projections. GPT did not rerun the local pytest suite or execute the Windows/Docker clean-clone command.

## Decision

**R1.10 core evidence reconciliation and algorithm-fidelity repair are accepted with remediation.** The main numerical reconciliation is independently reproducible from committed projections; the historical R1.9 conclusion remains exploratory and shows no evidence of CEA-v2 superiority. Do not authorize Phase 5 or a paid pilot. R1.11 is required to make the post-hoc sensitivity analysis reproducible from committed source code and to clean up contradictory status metadata.

## Independent checks passed

### 1. Task projection and success-rate recomputation

From \`results/phase4/r19-audit/auditable_tasks.jsonl\`:

- 208 rows, 26 unique tasks, seeds 20261014 and 20261015, four arms with 52 rows each.
- 208 unique \`(task_id, seed, arm)\` keys; no duplicate keys.
- Recomputed final successes: B0 43/52 = 0.826923; B1-random 47/52 = 0.903846; B5-v1 47/52 = 0.903846; CEA-v2 45/52 = 0.865385.
- Row-level \`provider_calls\` sum to 699; arm totals are 163, 180, 185, and 171.
- R1.9 historical row costs remain the original whole-episode/off-peak reporting convention; they were not retroactively rewritten to CEA-v2.1 incremental-cost semantics.

### 2. Ledger reconciliation and budget cap

From \`results/phase4/r19-audit/auditable_ledger.jsonl\`, independently recomputed in this review:

- 2,755 ledger transition rows.
- 913 unique request IDs: 912 final SETTLED and one final UNKNOWN.
- Sum of SETTLED \`cost_cny\`: **CNY 1.3063390536**.
- The one UNKNOWN reservation upper bound: **CNY 0.15704064**.
- Total conservative spend: **CNY 1.4633796936 < CNY 2.00**.
- The relevant aborted final-pilot scope accounts for the row-level difference of six attempts: 693 SETTLED + 1 UNKNOWN + 5 gate-stopped REJECTED = 699. There are 11 REJECTED transition records across all runs; the five in this formula refer specifically to the affected scope, not all runs.

These figures match the reconciled manifest to rounding. This independently verifies arithmetic from committed cost/reservation transitions; it does not independently reprice every request from token buckets because the proxy ledger schema does not persist per-request token counts or pricing-tier details.

### 3. Controller-event coverage

The committed projection has five controller events: four behavioral observations and one evolve event. The four behavioral event episode IDs match exactly the four CEA-v2 task rows with controller updates; no missing or extra episode IDs were found.

The R1.9 historical evolve event itself does **not** contain the new \`nsga3_parent_selection_calls\` / \`nsga3_survivor_selection_calls\` fields: those were added after the live experiment. The count of zero is reconstructed from the frozen R1.9 code path and archived controller state, not from a counter emitted during the historical run. The reconstruction is sound: exactly four candidates were measured, all four became parents directly, and population size eight did not exceed the limit of 16. Neither parent nor survivor selection invoked NSGA-III. Future evolve events now carry explicit counters and three regression tests cover the branches.

### 4. CEA-v2.1 source review

The current \`run_row\` implementation snapshots provider-attempt count and known cost after attempt 1, then passes only attempt-2 incremental cost/calls to the controller for behavioral observations. A no-op intervention records one failed behavioral observation with zero incremental cost/calls and makes no retry. Infrastructure/unknown-cost outcomes do not enter behavioral fitness. Controller version is \`cea-v2.1-r1.10\`. Historical R1.9 rows and events remain unchanged.

The Executor reports 623/623 tests passed and clean-clone passed at 5d5777c. Those results are not independently rerun by GPT in this review.

### 5. Independent exact check of the cluster-aware sensitivity

The committed \`sensitivity.json\` reports Monte Carlo sign-flip values from 20,000 permutations. I independently reconstructed the 26 task-level mean paired differences from the 208 task rows and exactly enumerated all \(2^{26}\) sign assignments using their discrete support. The exact two-sided sign-flip values are:

| Comparison | Reported 20,000-permutation estimate | Exact sign-flip value |
|---|---:|---:|
| CEA-v2 vs B1-random | 0.7462 | 0.750000 |
| CEA-v2 vs B5-v1 | 0.62095 | 0.625000 |
| CEA-v2 vs B0-original | 0.7268 | 0.7265625 |

The Monte Carlo values are compatible with exact enumeration and all conclusions remain non-significant. This independently validates the numerical direction and conclusion, but the committed repository currently lacks code that regenerates the post-hoc sensitivity file; R1.11 must close that reproducibility gap.

## Findings requiring R1.11

### P1 — The post-hoc sensitivity result has no committed generating script

\`scripts/analyze_r19_pilot.py\` computes the preregistered McNemar/cluster-bootstrap analysis but contains no sign-flip permutation implementation. \`scripts/build_r19_audit.py\` creates the three audit projections and reconciled manifest but does not generate \`sensitivity.json\`. No committed source was found that reproduces the 20,000-permutation result.

Remedy: add a deterministic analysis script and tests. Prefer exact dynamic-programming enumeration over the 26 task clusters, producing exact values 0.75, 0.625 and 0.7265625, with a clear post-hoc/sensitivity label. Include the sensitivity file and generating script hash in the reconciled manifest. Do not alter the preregistered R1.9 analysis.

### P2 — Status metadata remains internally stale despite the claimed normalization

At reviewed HEAD, \`status.json\` still contains contradictory top-level metadata:

- \`planner_review\` says R1.9 is “NOT_INDEPENDENTLY_REPRODUCIBLE,” although R1.10 now commits the audit projections and the arithmetic is reproducible from them.
- \`notes\` still says request/cost totals are not verifiable until projections are committed, which is outdated.
- \`tests.clean_clone_tested_sha\`, \`tests.current_remote_head\`, and \`tests.final_head_clean_clone_status\` still refer to the older d2a4235/62d9738 state, while the nested R1.10 section correctly reports clean-clone at 5d5777c and current HEAD 2bb9e5c.
- \`tests.categories.online_evolution_controller\` says 16/16 while the Executor report says 19 passed.
- The top-level review path still points to the R1.7 review rather than the current R1.10 review.

Remedy: preserve the old R1.9/R1.7 review history under explicit historical keys, but make the current top-level review, test SHAs, test counts, limitations, and notes consistent with R1.10 and the next R1.11 gate.

### P2 — Audit field definitions overstate the projection's token-level detail

The current proxy ledger implementation persists lifecycle state, scope, reservation, settled cost and safe notes; it does not persist per-request token buckets or pricing tier. The task projection does contain row-level aggregate input/cache/output token counts, but these cannot be mapped back to every proxy request. Do not invent per-request usage. Add an explicit manifest limitation stating that the round total is independently recomputed from settled ledger costs plus the UNKNOWN reservation bound, while per-request token-level repricing is unavailable from the source ledger.

The task projection intentionally retains \`intervention_text\` for action-level auditability. Replace blanket statements such as “no prompts” with the precise claim “no raw request/response bodies, full provider payloads, credentials or raw session logs; selected intervention text is retained in the sanitized task projection.”

### P2 — Make the historical NSGA-III evidence wording precise

Keep the correction that R1.9 invoked NSGA-III zero times. Also explicitly state that the historical event lacks the post-hoc invocation counters and that the zero is reconstructed from the old source branch conditions plus archived state; the new counters apply to future runs. This avoids implying that R1.9 emitted telemetry it did not emit.

## Final review status

- R1.9 data and cost arithmetic: **PASS from committed projections**.
- Historical NSGA-III claim correction: **PASS**, with the telemetry caveat above.
- CEA-v2.1 incremental fitness/no-op implementation: **source review PASS; tests Executor-reported, not rerun by GPT**.
- Post-hoc sensitivity numeric conclusion: **independent exact check PASS; reproducibility source missing**.
- Status metadata: **needs correction**.
- New live calls / spend authorized: **0 / CNY 0**.
- Phase 5 / paid pilot: **not approved**.

Next plan: \`CE-DSH-P4-R1.11\` — sensitivity reproducibility and status closure.