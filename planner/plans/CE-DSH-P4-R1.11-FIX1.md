# CE-DSH-P4-R1.11-FIX1 — Preserve Historical Estimates and Close Final-SHA Gate

Baseline: \`d92165c321a670c723f01f616be8b5703386bc7a\`
Independent review: \`planner/reviews/CE-DSH-P4-R1_11-independent-review.md\`

## Hard boundary

**Offline-only. Zero real DeepSeek API calls, zero new spend, no balance queries.** Do not run \`--live\`, \`--canary\`, or any model request. Do not enter Phase 5 or a paid pilot.

## Task A — Restore and preserve R1.10 Monte Carlo estimates

The current \`sensitivity.json\` has an empty \`previous_monte_carlo_estimates\` object. Restore the three historical records from \`sensitivity.json\` at commit \`2bb9e5c3e6f9ac8c01e9f2529d4939459b055b1e\`:

- CEA-v2 vs B1-random: p=0.7462, stat=-0.038461538461538464, n_clusters=26, n_permutations=20000, seed=20261026.
- CEA-v2 vs B5-v1-frozen-pareto: p=0.62095, stat=-0.038461538461538464, n_clusters=26, n_permutations=20000, seed=20261026.
- CEA-v2 vs B0-original: p=0.7268, stat=0.038461538461538464, n_clusters=26, n_permutations=20000, seed=20261026.

Use a stable source of truth: either add a small immutable historical-estimates artifact with provenance and a manifest hash, or define a clearly documented frozen constant copied from the historical artifact. Do **not** read the generated \`sensitivity.json\` as the sole source of the previous estimates; that design loses the records after a second run.

Update \`scripts/analyze_r19_cluster_sensitivity.py\` so every run emits the same exact results **and** all three historical estimates. Update \`results/phase4/r19-audit/sensitivity.json\` and \`manifest_reconciled.json\` hashes accordingly.

Strengthen \`tests/test_cluster_sensitivity.py\`:
- assert all three exact historical records and metadata are present, not merely that the key exists;
- run generation twice and assert byte-identical output;
- after both runs, assert the historical estimates remain unchanged;
- retain the current exact p-value, cluster/seed, validation, tie-handling and post-hoc-label tests.

## Task B — Normalize status metadata

Update \`status.json\` against the current baseline \`d92165c321a670c723f01f616be8b5703386bc7a\`:

- Set the current planner-review state to \`R1.11_REQUEST_CHANGES_HISTORICAL_ESTIMATES_STATUS_AND_EXACT_SHA_GATE\` (or equivalent explicit wording).
- Set \`phase_status=READY_FOR_EXECUTION\`, \`next_actor=Kimi-Executor\`, \`baseline_main_sha\` to this fix-round baseline, and \`review_path=planner/reviews/CE-DSH-P4-R1_11-independent-review.md\`.
- Distinguish the R1.11 code/data commit \`3ecd7691e8d93d8357b60531e1722b1d5ba4e044\` from the current docs-only HEAD \`d92165c321a670c723f01f616be8b5703386bc7a\`.
- Update \`tests.current_remote_head\`, \`tests.planner_reviewed_head\`, \`tests.clean_clone_tested_sha\`, and \`tests.final_head_clean_clone_status\` without claiming that d92165c has already been tested.
- Correct all stale 623-pass limitations to 631 Executor-reported passes / 0 failures / 0 skips. State explicitly that GPT has not independently rerun pytest.
- Preserve R1.10 and R1.11 historical metadata in explicit history fields; do not erase old audit trail.
- Update \`blockers\`, \`limitations\`, \`notes\`, \`next_goal\`, \`reviewed_executor_head\`, and test categories so the status has one coherent interpretation.

## Task C — Verification and final-SHA gate

- Run the sensitivity generator twice; verify identical output bytes and verify all historical estimates remain populated.
- Run \`pytest tests/test_cluster_sensitivity.py -q\`, \`tests/test_analyze_r19.py\`, \`tests/test_online_evolution.py\`, and \`tests/test_incremental_fitness.py\`.
- Run full \`pytest tests/ -q\`; report exact current counts rather than assuming 631.
- Recheck 208 unique task rows, 26 clusters with both seeds, 2,755 ledger transitions, contiguous \`seq\` within each run, 912 SETTLED, one UNKNOWN, CNY 1.3063390536 settled + CNY 0.15704064 UNKNOWN bound = CNY 1.4633796936.
- Recompute the sensitivity script/output SHA-256 and update \`manifest_reconciled.json\`.
- Verify frozen hashes, Phase 0–3 and historical task projection unchanged; run secret scan and inspect final diff.
- Push all code, tests, manifest, output, docs and status changes.
- Run \`python scripts/clean_clone_check.py <EXACT_CURRENT_ORIGIN_MAIN_SHA>\` **after the last commit has been pushed**. The exact current \`origin/main\` SHA must match the tested SHA.
- Do not create another commit after the exact-current-HEAD gate. Report the exact tested SHA and output in the final response. If any commit is made after the gate, rerun it against the new HEAD.

If the estimates are still empty, any historical outcome/hash changes unexpectedly, status fields conflict, or the exact-SHA gate fails, stop and report BLOCKED.

## Deliverables

- Corrected sensitivity generator/output with all historical Monte Carlo records preserved.
- Strong regression tests proving preservation and byte-identical regeneration.
- Updated manifest with accurate script/output/historical-artifact hashes and token limitation.
- Consistent status metadata and executor report.
- Exact final-SHA clean-clone evidence and final test counts.

## Required final answers

1. Are the three historical Monte Carlo records present after two generator runs?
2. Are the output bytes identical and do exact p-values remain 0.75, 0.625, 0.7265625 and 1.0?
3. Are status fields consistent with the current HEAD and the actual clean-clone-tested SHA?
4. What are the exact final SHA, clean-clone result and test counts?
5. Are frozen data and spend unchanged, with zero API calls?

Next actor: GPT-Planner.