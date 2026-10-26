# CE-DSH-P4-R1.9 — GPT Planner Independent Review

- Repository: yujian777555/CausalEvo-DSH
- Reviewed HEAD: 62d9738281b9f4c3186ef09ea711c61cb8ad361a
- Experiment implementation: 45c51eb66c2c30ef34693278f15cf415193c3424
- Experiment report/data summary: d2a42357ecd353d9502ce04b92feffcee1379265
- Final docs/status follow-up: 62d9738281b9f4c3186ef09ea711c61cb8ad361a
- Decision: **Accept that an exploratory four-arm live pilot was reported as completed; do NOT accept the package as independently reproducible, and do NOT accept the claim that NSGA-III selection was exercised in the live pilot.**
- Method: GitHub source/artifact review only. GPT did not independently rerun the Windows/Docker test suite or query the provider. Reported tests and live-call totals remain executor-reported.

## Summary of reported outcome

The committed analysis summary reports 208 task rows (26 tasks × 2 seeds × 4 arms), final success rates B0 0.8269, B1-random 0.9038, B5-v1-frozen-pareto 0.9038, CEA-v2-online 0.8654. It reports CEA-v2 versus B1 difference -0.038, McNemar p=0.6875 and task-cluster bootstrap CI [-0.154, 0.058]. The result is exploratory and provides no evidence of superiority. The report claims 912 settled requests plus one unknown-cost request bounded at CNY 0.157041, for CNY 1.463380 total against the authorized CNY 2.00 cap. These aggregates cannot yet be independently reconciled from the committed artifacts.

## Findings

### P0 — Required task/event/ledger evidence is absent from the Git tree

At reviewed HEAD, results/phase4/live2/phase4-r19-pilot-20261024T151323Z contains analysis.json, controller_state.json, manifest.json, and proxy-ledger control files. It does NOT contain the reported tasks.jsonl, events.jsonl, or proxy-ledger/ledger.jsonl. The repository .gitignore ignores *.jsonl and has no committed R1.9 auditable projection. The 208 individual rows, event chronology, request-level settlement history and cost total therefore cannot be independently recomputed from GitHub.

Do not infer that local files are lost; they may still exist on the Executor machine. But the current GitHub artifact package is insufficient. Publish sanitized, hashed audit projections from the original local files, if they exist. If they do not exist, state NOT_REPRODUCIBLE and do not fabricate replacements.

### P0 — The live pilot did not invoke NSGA-III selection in its only evolution event

Source: src/causalevo/evolution/online_evolution.py, _evolve().

The controller chooses n_parents = min(4, len(measured)). It calls nsga3_select for parents only when len(measured) > n_parents. The committed controller_state.json shows exactly four measured candidates at the only evolution event. Thus all four measured candidates are used as parents and no NSGA-III parent selection is invoked. The population grows from four measured candidates to eight total, below max_population=16, so the survivor-selection branch does not invoke NSGA-III either.

Conclusion: the live run performed crossover/mutation and a population-version update, but its only live evolution event did not exercise NSGA-III selection. Correct the formal report/addendum. Do not describe this pilot as live validation of NSGA-III or its contribution. This does not invalidate separate offline NSGA-III tests.

### P1 — The controller's cost/call fitness uses whole-episode totals, not incremental intervention cost

Source: scripts/run_phase4_r19_pilot.py, run_row().

After the retry, controller.observe receives budget.ledger.known_cost_cny and budget.ledger.provider_attempts. Both include the first attempt that occurred before an intervention was selected. The controller fitness then averages those totals. This does not implement the intended incremental-cost/call objective and can confound action comparisons because baseline attempt costs differ by task.

For future code, snapshot cost/calls after attempt 1 and send only attempt-2 incremental cost/calls to the controller. Preserve R1.9 observations as historical; do not rewrite them to look as though they used incremental costs.

### P1 — No-op phenotype returns before observe()

Source: scripts/run_phase4_r19_pilot.py, run_row().

If genome_to_text() returns None, run_row returns immediately without calling controller.observe(). An empty/no-op phenotype can therefore be selected without receiving an outcome update. Check the original task rows to determine whether this occurred in R1.9. For future runs, define explicit no-op semantics and feed the settled failure/zero incremental cost/zero incremental calls back to the selected no-op candidate, without making an extra model request.

### P1 — Row and request accounting do not reconcile

- manifest.json reports rows=58, while analysis.json reports rows_total=208. The runner's rows variable counts only rows newly executed by the last process, but the field name does not disclose that meaning.
- Summing the committed per-arm provider_calls gives 163 + 180 + 185 + 171 = 699. The report's request-count decomposition attributes 693 requests to the formal pilot and resume. Difference: six requests.
- manifest proxy_final.settled_cost_cny is 0.9948804852 for the recorded run scope, while the overall report states CNY 1.306339 settled across this round, plus CNY 0.157041 unknown bound. Multi-run accounting may explain the difference, but the missing ledgers prevent verification.

Reconcile all R1.9 canary, aborted-run, resumed-run and final-run request IDs. Distinguish logical requests, provider attempts, SETTLED requests and UNKNOWN requests. Verify the total reserved/settled/unknown amounts against the CNY 2.00 cap without double-counting or resetting any ledger. Preserve the original manifest and add a reconciled manifest with explicit field semantics and a hash link to the original.

### P1 — McNemar p-values do not account for the two-seeds-per-task clustering

The protocol uses McNemar on 52 task-seed pairs, but the two seeds belong to only 26 task clusters. The reported confidence interval resamples tasks, but the exact McNemar p-value still treats the discordant pairs as independent. The reported result is non-significant, so this does not create a positive claim; however, the p-value should not be treated as cluster-adjusted confirmatory evidence.

Preserve the preregistered McNemar results as the original analysis. Add a clearly labeled cluster-aware sensitivity analysis (e.g. task-level paired permutation/sign-flip on the two-seed task means) and require a cluster-aware primary test for any future confirmatory protocol. Do not silently replace the preregistered endpoint after seeing results.

### P2 — status.json has duplicate top-level blockers keys and stale metadata

The committed status.json contains two top-level blockers keys. JSON parsers commonly keep only the last value, making the status ambiguous across tooling. It also retains stale R1.7 planner_review/live-readiness metadata even though R1.9 has completed. Normalize the JSON to unique keys, preserve historical R1.7 review data under its historical section, and make the current R1.9 decision explicit.

## Git/test scope

- Current remote HEAD is 62d9738281b9f4c3186ef09ea711c61cb8ad361a.
- Executor reports 616 passed, 0 failed, 0 skipped.
- Clean-clone and historical 312-row reconciliation passed at d2a42357ecd353d9502ce04b92feffcee1379265. The later 62d9738 commit changes status.json and executor_report.md only; the exact final HEAD was not clean-clone tested.
- GPT did not independently rerun tests.
- Historical Phase 0–3 and old 312-row results are reported unchanged; retain their frozen status.

## Final decision

R1.9 is accepted only as a **reported exploratory pilot with no demonstrated CEA-v2 benefit**. It is not accepted as a fully reproducible evidence package, and it does not demonstrate live NSGA-III selection. No additional live API calls are authorized by this review. Next phase R1.10 is evidence reconciliation and algorithm-fidelity correction only, with zero new API spend.