# CE-DSH-P4-R1.12-REVIEW-FIX1 — GPT Planner Independent Review

- Repository: yujian777555/CausalEvo-DSH
- Reviewed current origin/main: c436de3086c31c6f7bdb21a32c83b06b7c173ed4
- Code/test commit: 9488a3f7f9ddde10442e0d25e4c1ebded1fc574e
- Follow-up commit: c436de3086c31c6f7bdb21a32c83b06b7c173ed4
- Decision: **REQUEST CHANGES — offline audit closure only**
- Live API calls authorized by this review: **0**.

## Review method and limits

I inspected the current main ref, commit metadata/diff, R1.12 analysis code, hash builder/verifier, reconciled manifest, protocol, status metadata, executor report, and new regression tests through the GitHub repository connector. I did **not** run local pytest, clean-clone, or a fresh local recomputation in this review turn. The 655-pass suite and prior clean-clone output remain Executor-reported.

The previous independent review's raw-data findings remain valid: 208/208 rows, the reported rates and exact cluster p-values match the previously inspected committed data; total R1.12 canary+pilot ledger is 738 settled requests / CNY 1.0397171982, with UNKNOWN bound 0. The scientific conclusion remains no evidence of improvement; live NSGA-III parent/survivor selection calls were both zero.

## Findings

### P1 — The exact-final-SHA gate did not run on current main

Current main is c436de3086c31c6f7bdb21a32c83b06b7c173ed4. Its parent is 9488a3f7f9ddde10442e0d25e4c1ebded1fc574e. The diff for c436de changes planner/executor_report.md and status.json after the reported clean-clone output, which explicitly tested 9488a3f..., not c436de...

Therefore, the required final gate is **not satisfied**. The executor report's statement that the follow-up commit was made after the final gate while no commits occurred after that gate is internally contradictory. The user-provided summary's claim that clean-clone passed at c436de is not supported by the committed report; the report records PASS only at 9488a3f.

The gate must be rerun after all code, tests, manifest, status, and report edits are complete, with the exact SHA equal to the then-current git ls-remote origin main. No commit may follow that gate.

### P1 — The hash verifier's path-boundary check can be bypassed within the repository

In scripts/verify_r12_hashes.py, the verifier first checks whether the raw path starts with an allowed prefix, then only checks str(resolved_path).startswith(str(REPO)). A path such as:

results/phase4/live2/../../../status.json

passes the raw-prefix check and resolves inside the repository, so it passes the repository-prefix check despite escaping the permitted artifact root. This contradicts the documented fail-closed path-traversal guarantee.

Use canonical resolved paths and require each resolved path to be a descendant of one of the specific allowed roots (e.g. via Path.relative_to), not merely a string-prefix match. Add a regression test for traversal from an allowed prefix to another repository file, plus symlink escape where supported.

### P1 — The independent verifier does not enforce the required artifact inventory

scripts/verify_r12_hashes.py verifies only the entries present in the manifest. If a required entry is removed from artifacts, verification can still return success for the smaller set. The current test checks that the committed manifest has 12 keys, but does not test that the verifier rejects a manifest with a required key removed.

Make the verifier enforce the exact required label set (the 12 expected artifacts) and reject missing, unexpected, malformed, or duplicate/ambiguous entries. Add a test proving that deleting pilot_ledger or another required entry is rejected.

### P2 — Holm-adjusted values are mapped to the wrong comparisons for nontrivial p-values

In scripts/analyze_r12_replication.py, p-values are sorted independently, then holm_step_down returns adjusted values in sorted-p order. The result is assigned using zip(sorted(secondary), adjusted), where sorted(secondary) sorts comparison names lexicographically, not by their raw p-values. Thus adjusted values can be attached to the wrong comparison whenever the three secondary p-values differ and yield nonidentical adjusted values. Current observed adjusted values are all 1.0, so the present conclusion is unaffected, but the analysis implementation is not generally correct.

Return a mapping from comparison key to adjusted p-value, or sort (raw_p, comparison_key) pairs and restore results to their original comparison keys. Add an integration test with distinct, nontrivial p-values that checks each comparison receives its mathematically correct Holm-adjusted p-value—not only that the standalone function returns a sorted list.

### P2 — The R1.12 analysis output embeds a machine-specific absolute path

The committed analysis.json has run_dir set to D:\CausalEvo-DSH\results\.... Re-running the analysis from a clean clone or a different workspace will write a different run_dir and therefore change analysis.json and its recorded SHA-256 even if the underlying rows and statistics are identical.

Normalize this field to a stable repository-relative POSIX path (or another documented deterministic identifier), regenerate only the derived analysis.json and reconciled manifest, and verify that two runs produce byte-identical output. Do not modify the raw tasks, events, or proxy ledger.

### P2 — Status/report fields are stale or contradictory

At current main c436de, status.json still records current_remote_head=9488a3f..., although the actual main ref is c436de.... It also reports phase_status=READY_FOR_REVIEW while clean_clone_final is PENDING_FINAL_GATE, and blockers=[] despite the exact-SHA gate being pending. The executor report records a gate at 9488a3f... but describes it as the final gate.

Update status/report only after all fixes are complete. Distinguish the tested code commit from the actual final SHA and explicitly mark the gate pending until it is executed on that final SHA. The final gate must include the final status/report bytes.

## Required next action

Run **CE-DSH-P4-R1.12-REVIEW-FIX2**, offline-only:

1. Fix path containment and required-manifest-inventory enforcement in the hash verifier.
2. Fix the comparison-to-Holm-adjusted-p mapping and add an integration regression test.
3. Normalize the analysis output path and test deterministic regeneration.
4. Correct status/report metadata and preserve all historical records.
5. Run focused tests and the full pytest tests/ -q suite.
6. Commit and push all changes; confirm HEAD = git ls-remote origin main and the worktree is clean.
7. Run clean-clone against that exact final remote SHA. **Do not commit anything afterward.** If any post-gate edit is unavoidable, rerun the gate on the new final SHA.

No live API calls, no balance queries, no new pilot, and no Phase 5. Preserve all R1.12 raw rows/ledgers and Phase 0–3/R1.9 frozen artifacts byte-for-byte.

## Scientific interpretation

- Primary CEA-v2-online vs B1-random: paired difference 0, unadjusted exact cluster p = 1.0, reported 95% CI [-0.076923, 0.076923].
- The three secondary comparisons remain non-significant under the corrected Holm family.
- NSGA-III parent and survivor selection calls in the live run: both 0.
- No evidence of CEA-v2 superiority, no unseen-task generalization claim, and no L4 RSI claim.

The R1.12 data are useful and should be retained; this decision concerns audit closure and implementation correctness, not a request to repeat the experiment.
