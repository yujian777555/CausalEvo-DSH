# CE-DSH-P4-R1.11 — GPT Planner Independent Review

- Repository: \`yujian777555/CausalEvo-DSH\`
- Reviewed current remote HEAD: \`d92165c321a670c723f01f616be8b5703386bc7a\`
- R1.11 code/data commit: \`3ecd7691e8d93d8357b60531e1722b1d5ba4e044\`
- Method: direct source/artifact inspection, independent recomputation from the committed task projection, ledger reconciliation and status metadata inspection.
- GPT did **not** independently run the local pytest suite or clean-clone command; the 631-test and 3ecd clean-clone results remain Executor-reported.

## Decision: REQUEST CHANGES

The exact cluster sign-flip implementation is mathematically sound for the committed 208-row projection, the cost reconciliation remains correct, and the token-ledger limitation is disclosed. However, R1.11 is **not accepted yet** because the previously reported Monte Carlo estimates are not actually preserved in the current output, status metadata is still stale, and the required exact-current-HEAD clean-clone gate was not run.

No Phase 5 or paid pilot is authorized. No new live API calls or spend are authorized.

## Independently verified

### Task clusters and exact sign-flip values

- \`auditable_tasks.jsonl\`: 208 rows and 208 unique \`(task_id, seed, arm)\` keys.
- 26 task clusters; each cluster contains both seeds \`20261014\` and \`20261015\`; all four arms are present for each seed.
- I independently recomputed the task-level paired outcome differences from the 208 rows and enumerated the full sign-flip distribution over \(2^{26}=67,108,864\) assignments.
- Exact two-sided p-values match the committed output:
  - CEA-v2 vs B1-random: **0.750000**
  - CEA-v2 vs B5-v1-frozen-pareto: **0.625000**
  - CEA-v2 vs B0-original: **0.7265625**
  - B5-v1-frozen-pareto vs B1-random: **1.000000**
- The DP method in \`scripts/analyze_r19_cluster_sensitivity.py\` correctly accumulates the discrete signed-sum distribution and includes ties in the two-sided tail. The post-hoc label is appropriate; this does not replace the preregistered McNemar analysis.

### Ledger and audit boundary

- 2,755 ledger transitions; \`seq\` is contiguous from zero within each of the five runs.
- 913 unique request IDs; 912 final SETTLED and one final UNKNOWN.
- SETTLED cost sum: **CNY 1.3063390536**.
- UNKNOWN reservation bound: **CNY 0.15704064**.
- Conservative total: **CNY 1.4633796936 < CNY 2.00**.
- The manifest correctly says the source proxy ledger does not persist per-request token buckets or pricing tier. Row-level aggregate token counts cannot be mapped to individual proxy requests; per-request token-level repricing is not reproducible.
- The NSGA-III documentation correctly distinguishes the reconstructed historical zero-call conclusion from counters added after the R1.9 run.

## Findings requiring correction

### P1 — Prior Monte Carlo estimates are missing from the current sensitivity output

At reviewed HEAD, \`results/phase4/r19-audit/sensitivity.json\` has:

\`\`\`json
"previous_monte_carlo_estimates": {}
\`\`\`

This contradicts the output's note and the Executor report saying the prior 20,000-permutation estimates were preserved.

I inspected the historical \`sensitivity.json\` at parent commit \`2bb9e5c3e6f9ac8c01e9f2529d4939459b055b1e\`. It contains these three estimates:

| Comparison | p | Statistic | Permutations | Seed |
|---|---:|---:|---:|---:|
| CEA-v2 vs B1-random | 0.7462 | -0.038461538461538464 | 20,000 | 20261026 |
| CEA-v2 vs B5-v1-frozen-pareto | 0.62095 | -0.038461538461538464 | 20,000 | 20261026 |
| CEA-v2 vs B0-original | 0.7268 | 0.038461538461538464 | 20,000 | 20261026 |

Root cause: the generator reads the current generated \`sensitivity.json\` as its source for historical values, then looks only for \`cluster_permutation_sensitivity\` in its comparisons. Once it writes the new exact-format output, that nested field is absent; a subsequent run replaces the previous estimates with an empty object. The current test checks only that the key exists, not that its contents are retained. The current output is deterministic, but the historical estimates were lost from the generated artifact.

**Required fix:** preserve the values from the historical R1.10 artifact in an immutable source (for example, a dedicated historical-estimates JSON with provenance to commit 2bb9e5c, or a versioned constant in the generator). Never use the generated output as the only source for data that must survive regeneration. Add assertions for the exact three p/stat/permutation/seed records and verify two successive regenerations are byte-identical *and* retain all three records. Update the script/output hashes in the manifest.

### P2 — \`status.json\` still contradicts the current repository and R1.11 report

At reviewed HEAD:

- \`tests.current_remote_head\` is \`3ecd7691...\`, but the actual current \`origin/main\` HEAD is \`d92165c3...\`.
- \`tests.clean_clone_tested_sha\` remains the R1.10 SHA \`5d5777c...\`, while the R1.11 report says the exact clean-clone passed at \`3ecd7691...\`.
- \`tests.final_head_clean_clone_status\` still describes \`2bb9e5c...\` as the current docs-only HEAD; that is stale.
- \`limitations\` still says the Executor-reported full suite had 623 passes, despite the R1.11 report and \`tests.passed\` reporting 631.
- \`planner_review\` still describes R1.10 remediation as outstanding rather than representing the current R1.11 review decision.
- \`tests.categories.clean_clone\` and the other head/test fields need to distinguish the R1.11 code/data SHA from the final docs-only HEAD.

**Required fix:** update current metadata to the actual fix-round baseline and latest HEAD; record 631 as Executor-reported, not GPT-rerun; preserve historical values under explicit historical keys; do not claim a clean-clone pass for a SHA that was not tested.

### P2 — Exact-current-HEAD clean-clone gate was not completed

The plan required clean-clone against the exact current \`origin/main\`. The report records a pass at \`3ecd7691...\`, followed by a docs-only commit to \`d92165c3...\`. The current HEAD is therefore not the SHA named in the reported clean-clone result.

The docs-only nature reduces implementation risk but does not satisfy the exact-SHA gate that was explicitly required. After the corrections are committed, run \`python scripts/clean_clone_check.py <EXACT_CURRENT_ORIGIN_MAIN_SHA>\` against the then-current final SHA. Do not make further commits after that terminal gate; report its exact SHA and output in the final Executor response. If any later commit is made, the gate must be rerun for the new HEAD.

## Scientific interpretation

R1.11 improves auditability and reproducibility; it does not establish a performance gain. The CEA-v2 success rate remains 45/52 (0.8654), below B1 and B5 at 47/52 (0.9038), and all cluster-aware p-values remain non-significant. The result remains exploratory. L4 recursive self-improvement remains unimplemented.

## Review status

- Exact sensitivity computation and cluster grouping: **PASS**.
- Ledger arithmetic, per-run sequence continuity and spend cap: **PASS**.
- Token-level limitation and historical NSGA-III telemetry wording: **PASS**.
- Prior Monte Carlo preservation: **FAIL — fix required**.
- Current status metadata: **FAIL — fix required**.
- Exact current HEAD clean-clone gate: **NOT VERIFIED**.
- New real API calls / spend authorized: **0 / CNY 0**.

Next plan: \`CE-DSH-P4-R1.11-FIX1\`. Stop at the Phase 4 boundary after the fixes and wait for GPT Planner review.