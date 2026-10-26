# CE-DSH-P4-R1.11 — Sensitivity Reproducibility and Status Closure

Baseline: \`2bb9e5c3e6f9ac8c01e9f2529d4939459b055b1e\`
Review: \`planner/reviews/CE-DSH-P4-R1_10-independent-review.md\`

## Hard boundary

**Zero new real DeepSeek API calls; zero new spend.** Do not run \`--live\`, \`--canary\`, any model request, or any balance query. R1.9 is complete. This is an offline analysis/reproducibility and metadata-closure phase only. A future live run requires new explicit user budget authorization.

## Task A — Make the post-hoc cluster sensitivity fully reproducible

1. Read the committed 208-row projection at \`results/phase4/r19-audit/auditable_tasks.jsonl\`; never touch the raw historical rows or regenerate them with modified semantics.
2. Add \`scripts/analyze_r19_cluster_sensitivity.py\` (or an equivalent clearly separated module) that computes task-level paired mean differences for each comparison, keeping both seeds of each task together.
3. Prefer an exact sign-flip calculation using dynamic programming over the 26 cluster differences. There are only 26 clusters; exact enumeration over the discrete support is feasible and avoids Monte Carlo noise.
4. The exact two-sided p-values expected from the committed rows are:
   - CEA-v2 vs B1-random: 0.750000
   - CEA-v2 vs B5-v1-frozen-pareto: 0.625000
   - CEA-v2 vs B0-original: 0.7265625
5. Add tests for:
   - exactly 26 task clusters and both seeds retained in each cluster;
   - deterministic exact results above;
   - correct two-sided tail/tie handling;
   - missing arm, duplicate \`(task_id, seed, arm)\`, and missing-seed rejection;
   - explicit label \`POST_HOC_CLUSTER_AWARE_SENSITIVITY\`, not the preregistered primary test.
6. Regenerate \`results/phase4/r19-audit/sensitivity.json\` from the script. Preserve the previously reported 20,000-permutation estimates in a clearly named field if useful; do not silently replace or relabel them. Add exact values and method to the JSON.
7. Add the sensitivity script SHA-256 and output file SHA-256 to \`manifest_reconciled.json\`. Avoid self-referential hashes; the manifest may hash the script/output, but neither script nor output should attempt to hash the manifest as part of its own content.
8. Do not change the R1.9 preregistered McNemar values, success rates, task outcomes, costs, event log, or the exploratory conclusion.

## Task B — Clarify audit-ledger data limits without inventing fields

1. Inspect \`src/causalevo/eval/budget_proxy.py\` and the original ledger schema. The proxy ledger records lifecycle state, scope, reservation, settled cost and safe notes; it does not currently persist per-request token buckets or pricing tier.
2. Do not fabricate per-request token counts or claim per-request repricing is independently reproducible.
3. Update \`manifest_reconciled.json\` field definitions and \`docs/PHASE4_R1_9_RECONCILIATION.md\` to distinguish:
   - independently reproducible settled-cost sum + UNKNOWN reservation bound;
   - row-level aggregate token buckets in \`auditable_tasks.jsonl\`;
   - unavailable per-request token-level repricing because those fields were never persisted in the source ledger.
4. If useful, add a deterministic \`seq\` field to each sanitized ledger transition, preserving source-file order within each run. Keep all state transitions, request IDs when present, scopes, reservation/cost values and safe error reasons.
5. Keep \`intervention_text\` in the task projection for action-level auditability, but correct any blanket claim that no prompts are present. State precisely that raw request/response bodies, full provider payloads, credentials and raw session logs are excluded; the selected intervention text is intentionally retained.
6. Rebuild projections only if a byte-for-byte source-to-projection change is required; do not modify historical task outcomes or cost records. If projection format changes, update hashes and rerun all audit checks.

## Task C — Make status.json authoritative and internally consistent

1. Preserve old R1.7/R1.9 review history under explicit historical keys.
2. Update current top-level \`planner_review\`, \`review_path\`, \`phase\`, \`phase_status\`, \`next_actor\`, \`next_goal\`, and \`baseline_main_sha\` to the current R1.11 state.
3. Correct stale test metadata:
   - \`tests.categories.online_evolution_controller\` should match the actual Executor output (19 passed, if confirmed);
   - distinguish code/data SHA \`5d5777c80713356e2c0e2049e94e8499f8dc16dd\` (clean-clone tested) from current docs-only HEAD \`2bb9e5c3e6f9ac8c01e9f2529d4939459b055b1e\`;
   - update \`tests.current_remote_head\` and \`tests.clean_clone_tested_sha\`;
   - explicitly say the current docs-only HEAD was not clean-clone tested yet.
4. Replace stale top-level notes that say the R1.9 projections are missing or cost totals cannot be verified. Keep historical notes, but mark them as pre-R1.10.
5. Update limitations to state current facts: no GPT independent local pytest rerun; no CEA-v2 superiority evidence; L4 RSI not implemented; per-request token repricing unavailable from source ledger; post-hoc sensitivity is now script-reproducible after Task A.
6. Verify JSON parsing and ensure unique keys. Do not delete historical evidence or frozen-state references.

## Task D — Clarify historical NSGA-III telemetry

Update \`docs/PHASE4_R1_9_CORRECTION_ADDENDUM.md\` and/or \`docs/PHASE4_R1_10_ALGORITHM_FIDELITY.md\` to say explicitly:
- R1.9's historical evolve event does not contain the new NSGA-III invocation counters because instrumentation was added after the run;
- the zero-call count is reconstructed from the archived source logic (4 measured candidates, 4 parents, no overflow) and archived controller state;
- the newly added counters are for future events only.
Do not add synthetic counter fields to the historical event projection.

## Task E — Verification

- Run the exact sensitivity script twice and verify byte-identical JSON output.
- Run the focused sensitivity tests and existing R1.9 analysis/incremental-fitness/online-evolution tests.
- Run full \`pytest tests/ -q\`.
- Run \`python scripts/clean_clone_check.py <EXACT_FINAL_SHA>\` after the final commit is pushed, so the clean clone checks the exact current \`origin/main\`.
- Verify 208 task rows, 2755 ledger rows (or a documented count if projection sequence fields are added), 912 SETTLED, 1 UNKNOWN, CNY 1.3063390536 settled + CNY 0.15704064 unknown bound = CNY 1.4633796936, and no duplicate task keys.
- Verify frozen Phase 0–3 and historical 312-row hashes unchanged.
- Run secret scan and inspect final diff.
- Verify local HEAD == \`git ls-remote origin main\` and clean worktree.
- No model API calls, no balance queries, zero new spend.

If any historical artifact changes, counts drift, or exact sensitivity values fail, stop and report BLOCKED. Do not proceed to a live pilot or Phase 5.

## Deliverables

- Reproducible cluster sensitivity script + tests + regenerated \`sensitivity.json\`.
- Updated \`manifest_reconciled.json\` with sensitivity/script hashes and explicit per-request usage limitation.
- Corrected reconciliation/fidelity documentation and status metadata.
- \`planner/executor_report.md\` with exact final SHA, exact-SHA clean-clone output, test counts, frozen hashes, and remaining limitations.
- Push all changes and stop for GPT Planner review.

## Required final answers

1. Exact sign-flip p-values and proof both seeds stayed within 26 task clusters.
2. Does the sensitivity result regenerate deterministically from committed code?
3. Are ledger usage buckets present per request? If not, is the limitation explicit without invented data?
4. Are all status fields consistent with current HEAD and test results?
5. Does the historical NSGA-III note distinguish reconstructed zero calls from post-hoc instrumentation?
6. Exact final SHA, exact-SHA clean-clone result, test counts, frozen hashes and any blockers.

Next actor: Kimi-Executor.