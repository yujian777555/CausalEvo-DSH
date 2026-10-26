# CE-DSH-P4-R1.10 — R1.9 Evidence Reconciliation and Algorithm-Fidelity Repair

Baseline: 62d9738281b9f4c3186ef09ea711c61cb8ad361a
Independent review: planner/reviews/CE-DSH-P4-R1_9-independent-review.md

## Hard boundary

**Zero new real DeepSeek API calls; zero new spend.** The user-authorized R1.9 budget round is complete. Do not run --live, --canary, any balance query, or any model request. This phase repairs evidence, corrects the algorithm and analysis contracts, and prepares a future experiment proposal only. A future live run requires a new explicit user budget authorization.

## Objective

Do not run another experiment just to produce more numbers. First make the completed R1.9 pilot auditable and correct the implementation issues found in source review. Do not rewrite historical results or pretend the live pilot exercised NSGA-III when it did not.

## Task A — Recover and publish sanitized audit evidence

1. Fetch origin/main; record exact starting HEAD; inspect the R1.9 report, manifest, analysis, local run directories, and every canary/interrupted/resumed/final run ledger.
2. Locate the original local R1.9 tasks.jsonl, events.jsonl, and proxy-ledger/ledger.jsonl files. The current GitHub tree omits them because .gitignore ignores JSONL files.
3. If the originals exist, generate sanitized, deterministic projections without inventing or changing any outcome:
   - results/phase4/r19-audit/auditable_tasks.jsonl — exactly one row per final task/seed/arm observation, expected 208 rows.
   - results/phase4/r19-audit/auditable_events.jsonl — controller behavioral/infra/evolve events with lineage and event order.
   - results/phase4/r19-audit/auditable_ledger.jsonl — sanitized request state transitions across every R1.9 run needed to reconcile the full budget.
   - results/phase4/r19-audit/manifest_reconciled.json — hashes of original source files and projections, source run IDs, total rows, final-state counts by unique request_id, per-run and whole-round costs, UNKNOWN upper bound, and field definitions.
4. Never publish API keys, authorization headers, raw request/response bodies, full prompts, secrets, or irrelevant raw session logs. The ledger projection must preserve request_id, run_id, scope/episode identity, state transitions, reserved amount, settled amount, usage buckets, final state and safe error kind. If a field cannot be safely published, omit it and document the omission.
5. Add narrow .gitignore exceptions only for the sanitized audit projections. Do not broadly unignore raw JSONL files.
6. If local originals cannot be found or verified, stop the reconciliation claim: mark evidence as NOT_REPRODUCIBLE_FROM_GIT, document which originals are unavailable, and do not synthesize rows or ledger events.

## Task B — Reconcile the exact counts and money

Use unique request IDs and final state transitions, not guessed totals.

Must explain and reconcile:
- 912 claimed settled provider requests plus one UNKNOWN request.
- Sum of row-level provider_calls: 163 + 180 + 185 + 171 = 699.
- Report decomposition says 693 formal-pilot requests, leaving a difference of six.
- Final manifest rows=58 versus analysis rows_total=208.
- Final run manifest settled_cost_cny=0.9948804852 versus whole-round settled cost=1.306339.
- Unknown upper bound CNY 0.157041 and claimed total CNY 1.463380 versus the CNY 2.00 cap.

Separate canaries, interrupted runs, final pilot rows, retries, logical requests, provider attempts, SETTLED and UNKNOWN. Explain any legitimate overlap between resumed data and prior run directories. Verify that each logical request is counted exactly once in the final request total and that UNKNOWN is not double-counted in settled cost. Never edit original ledgers to make totals match.

Preserve the original manifest bytes and hash. Create a corrected manifest with unambiguous fields such as rows_total=208 and rows_written_last_process=58 only if verified. Add a reconciliation report with exact formulas and hashes.

## Task C — Correct the live algorithm-fidelity claim

1. Instrument nsga3_select invocation counts in the controller's evolve event and add regression tests for:
   - four measured candidates with no archive overflow;
   - more than four measured candidates;
   - archive overflow and survivor selection.
2. The R1.9 final controller state has four measured candidates, four offspring and max_population=16. Under the current code, neither parent selection nor survivor selection calls NSGA-III in the only live evolve event. Confirm this from the exact source/config and correct the R1.9 report via a dated correction/addendum. Do not claim the live pilot validated NSGA-III.
3. Preserve the distinction: the live pilot did exercise crossover/mutation/population update; separate offline tests may exercise NSGA-III. Report the actual operator invocation counts.

## Task D — Fix the intervention fitness measurements for future runs

1. In run_row, capture cumulative provider calls and cost immediately after attempt 1.
2. After attempt 2 settles, compute attempt-2 incremental calls and cost by subtracting the attempt-1 snapshot.
3. Pass incremental cost/calls to OnlineEvolutionController.observe and use them in candidate fitness. Retain both per-attempt and total costs in row records.
4. For a selected genome with no effective intervention text, define explicit no-op semantics. If no model retry is made, record final failure and zero incremental cost/calls as the no-op observation after accounting is settled; do not silently return without observe().
5. Add tests proving:
   - first-attempt costs do not enter candidate-specific intervention-cost fitness;
   - no-op selections are measured exactly once;
   - infra/unknown-cost cases never become behavioral rewards;
   - the same event log replays to the same state;
   - historical R1.9 observations are not rewritten as if these fixes were used.
6. Version the revised controller/fitness contract (e.g. CEA-v2.1 or a clearly versioned R1.10 implementation) so future experiments cannot be confused with R1.9.

## Task E — Statistical sensitivity and data validation

1. Recompute all reported success rates, discordant pairs, McNemar values, Holm adjustments, cost/call totals and confidence intervals from the sanitized 208-row projection.
2. Validate unique (task_id, seed, arm) keys, complete 26×2×4 coverage, no duplicates, no missing arms, consistent seeds and task hash.
3. Preserve the preregistered R1.9 McNemar analysis as the primary historical result.
4. Add a separately labeled cluster-aware sensitivity test at the task level (26 clusters; both seeds stay together), such as a paired sign-flip/permutation test on each task's mean success difference. Label it a sensitivity analysis performed after the pilot, not the preregistered primary test.
5. Keep the exploratory conclusion unchanged unless the verified data contradicts the summary. Any correction must be traceable to raw evidence.
6. Explain that two seed rows per task are clustered; future confirmatory studies need a cluster-aware primary inferential method.

## Task F — Repair status and report metadata

1. Normalize status.json so every object has unique keys; remove duplicate top-level blockers keys.
2. Preserve R1.7 review history, but update top-level planner_review, live_readiness, next_goal, current HEAD and R1.9 review decision to reflect the actual state.
3. Add docs/PHASE4_R1_9_RECONCILIATION.md and docs/PHASE4_R1_10_ALGORITHM_FIDELITY.md.
4. The R1.9 formal report must link to a dated correction note that explicitly states:
   - the current GitHub package omitted the raw task/event/ledger JSONL;
   - the manifest row count did not equal analysis row count;
   - request totals need reconciliation;
   - the sole live evolution event did not invoke NSGA-III selection;
   - the controller used whole-episode rather than incremental intervention cost/calls.
5. Never silently rewrite historical data or retroactively claim the corrected R1.10 implementation generated R1.9 outcomes.

## Task G — Required verification

- Focused tests for audit projection, count reconciliation, no-op feedback, incremental fitness and NSGA-III invocation counting.
- Existing online-evolution, adapter, statistics, budget proxy and security regression suites.
- Full pytest tests/ -q.
- Clean-clone verification on the exact final SHA.
- Hash checks for Phase 0–3 and historical Phase 4 312-row data.
- Secret scan.
- Verify local HEAD == git ls-remote origin main and clean worktree.
- No API calls, no balance queries, no new spend.

If originals are missing, count reconciliation cannot be proven, or any frozen artifact changes, stop and report BLOCKED. Do not proceed to another live pilot.

## Deliverables

- Sanitized audit projections and reconciled manifest, if source files are available.
- docs/PHASE4_R1_9_RECONCILIATION.md
- docs/PHASE4_R1_9_CORRECTION_ADDENDUM.md
- docs/PHASE4_R1_10_ALGORITHM_FIDELITY.md
- versioned corrected online controller and focused tests.
- Updated formal report links, status.json and planner/executor_report.md.
- Push all results and stop for GPT Planner review.

## Final response must answer

1. Can the 208 task rows be independently reconstructed from original files?
2. Are 912 settled requests, 699 row-level calls, and the six-call discrepancy reconciled?
3. Is the full-round CNY 1.463380 spend and CNY 2.00 cap independently verified?
4. Did R1.9 actually invoke NSGA-III? How many times?
5. Does candidate fitness use incremental intervention cost/calls after R1.10?
6. Are no-op selections measured?
7. What are the preregistered and cluster-aware sensitivity results?
8. Exact final tested SHA, clean-clone result, frozen hashes, and remaining blockers?

Next actor: GPT-Planner.