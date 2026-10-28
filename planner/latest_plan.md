# CE-DSH-P4-R1.12-REVIEW-FIX2 — Offline Audit Closure

Reviewed executor HEAD: `c436de3086c31c6f7bdb21a32c83b06b7c173ed4`
Review: `planner/reviews/CE-DSH-P4-R1_12-review-fix1-independent-review.md`
Decision: **REQUEST CHANGES**.
Next actor: Kimi-Executor.

## Absolute boundary

**Offline-only: zero new real API calls and zero new spend.** Do not rerun the live experiment or canary, do not query account balance, do not enter Phase 5, and do not alter historical R1.9 or Phase 0–3 frozen artifacts. R1.12 raw tasks, events, and proxy ledgers must remain byte-for-byte unchanged.

Before modifying anything, fetch the latest `origin/main`, inspect the Planner review commit and this plan, and verify the worktree is clean. Do not reset or overwrite any existing commits.

## Task A — Fix the final-SHA gate and status/report contradiction

The current main SHA at review time was `c436de3086c31c6f7bdb21a32c83b06b7c173ed4`, but the committed executor report records clean-clone PASS only for `9488a3f7f9ddde10442e0d25e4c1ebded1fc574e`. Commit `c436de` is a later status/report-only commit. Therefore the exact-final-SHA gate has **not** been demonstrated for current main, regardless of the user-facing summary.

- Keep the already reported 655-pass suite as Executor-reported until you actually rerun it.
- Normalize `status.json` and `planner/executor_report.md` to distinguish the code/test commit, previously tested SHA, current pre-fix SHA, and eventual final SHA.
- Do not mark the final gate PASS before running it on the exact final SHA.
- Keep the phase stopped at R1.12 offline review; no live work and no Phase 5.
- All status/report edits must happen **before** the final clean-clone command.

## Task B — Harden the R1.12 artifact hash verifier

Files:
- `scripts/verify_r12_hashes.py`
- `scripts/build_r12_manifest.py`
- `tests/test_r12_hashes.py`

Two gaps remain.

### B1. Enforce resolved path containment

The verifier checks the raw string prefix, then uses `str(resolved_path).startswith(str(REPO))`. This permits a path like `results/phase4/live2/../../../status.json`: it begins with an allowed raw prefix and resolves to another file inside the repository.

- Resolve all paths against the canonical repository root.
- Require the resolved path to be inside the specific allowed root corresponding to its artifact class, not just anywhere inside the repository.
- Use path-aware containment such as `Path.relative_to`, not string-prefix matching.
- Reject absolute paths, parent traversal, symlink escapes, malformed hashes, and paths outside the allowed artifact roots.
- Add tests for traversal from an allowed prefix to `status.json`, absolute paths, and symlink escape where supported.

### B2. Enforce the exact manifest inventory

The verifier currently loops only over entries present. Removing a required artifact entry can still leave the remaining entries valid.

- Require the exact 12 expected artifact labels.
- Reject missing labels, unexpected labels, malformed entries, and non-SHA256 values.
- Add a regression test that deletes a required label (e.g. `pilot_ledger`) and confirms verification fails.
- Keep the manifest deterministic and avoid self-referential hashes.
- Recompute and verify all 12 hashes after any permitted derived-artifact update.

Do not edit raw tasks/events/ledger files.

## Task C — Correct Holm result-to-comparison mapping

File: `scripts/analyze_r12_replication.py`

The standalone `holm_step_down` calculation uses cumulative maxima, but the integration code sorts the p-values and then assigns adjusted values by lexicographically sorted comparison names. For nontrivial p-values, this can attach an adjusted p-value to the wrong comparison.

- Preserve the association between each raw p-value and its comparison key.
- Sort (raw p-value, comparison key) pairs by raw p-value, calculate Holm step-down adjusted values, and write each adjusted value back to its originating comparison key. Handle ties deterministically.
- Keep the primary comparison `CEA-v2-online vs B1-random` unadjusted.
- Apply Holm only to the three preregistered secondary comparisons.
- Preserve the frozen estimand, task clustering, bootstrap seed/method, and raw data.

Add an integration regression test with distinct nontrivial secondary p-values, including a case where lexical comparison order differs from p-value order. Assert the correct adjusted p-value is assigned to each comparison key. A unit test that only checks the returned sorted list is insufficient.

The current observed secondary p-values are 1.0, 0.53125, and 1.0, with adjusted values all 1.0; this bug does not change the current scientific conclusion, but must be fixed for statistical correctness.

## Task D — Make R1.12 analysis output reproducible across clones

The committed `analysis.json` stores a machine-specific absolute Windows path in `run_dir`. Re-running the analyzer in a clean clone or another workspace changes that field and therefore changes the output hash even if all statistical results are identical.

- Store a stable repository-relative POSIX path (or another documented stable run identifier) in `analysis.json`.
- Re-run the analyzer against the existing R1.12 raw tasks without changing the raw task/event/ledger bytes.
- Rebuild `manifest_reconciled.json` and verify all 12 entries.
- Add a test that executes analysis twice in isolated output locations or with different checkout roots and proves normalized analysis output is byte-identical.
- Clearly distinguish deterministic derived output from immutable raw experimental data.

Do not change statistical definitions or task outcomes.

## Task E — Tests, preservation, and final gate

1. Add/adjust focused tests for path containment, exact artifact inventory, Holm key mapping, and deterministic analysis output.
2. Run the focused test suites, then the full `pytest tests/ -q`. Record exact output and exit code.
3. Verify the canonical task manifest hash remains `fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`, with exactly 26 tasks, seeds `20261027, 20261028`, four arms, 208 unique rows.
4. Verify the reconciled artifact manifest after the last derived-output regeneration. Confirm historical Monte Carlo source/provenance and Phase 0–3/R1.9 frozen artifacts remain unchanged; confirm R1.12 raw tasks/events/proxy ledger hashes are unchanged.
5. Run the secret scan and ledger reconciliation; report 738 settled requests, CNY 1.0397171982 settled cost, UNKNOWN bound 0, and zero new calls/spend only if confirmed by the committed evidence.
6. Finish all code, test, derived-artifact, manifest, status, report, and plan changes before the terminal gate.
7. Commit and push all changes. Verify local HEAD equals `git ls-remote origin main`, and the worktree is clean.
8. Run `python scripts/clean_clone_check.py <EXACT_FINAL_ORIGIN_MAIN_SHA>` using the exact SHA returned by the current `origin/main`. Verify the command itself confirms that SHA.
9. **Do not make any commit after the final gate.** If any change is needed after the gate, rerun the gate on the new final SHA. Do not write a post-gate “result-recording” commit.

If clean-clone does not run or fails, report the blocker honestly; do not claim PASS.

## Scientific conclusion and stop boundary

Preserve the narrow conclusion:

- Primary CEA-v2-online vs B1-random: paired difference 0, unadjusted exact cluster p = 1.0, reported 95% CI [-0.076923, 0.076923].
- No evidence of CEA-v2 superiority over random or static Pareto selection.
- Live NSGA-III parent-selection calls = 0 and survivor-selection calls = 0.
- Only 5 behavioral observations; no claim of reliable learned selection policy.
- Same-suite fresh-seed replication, not unseen-task generalization.
- L4 RSI is not implemented.

No additional API calls, no account balance query, no new pilot, and no Phase 5.

## Required final response

Report:
1. Fixes and changed files.
2. Regression-test results for path containment, required manifest labels, Holm key mapping, and deterministic output.
3. Raw-data preservation and all 12 artifact hashes verified.
4. Full test count and actual exit code.
5. Final commit SHA, remote equality, and clean worktree.
6. Exact final-SHA clean-clone command/output/exit code.
7. Zero new API calls and zero new spend.
8. Remaining limitations and explicit no-Phase-5 statement.

After all gates pass, set `phase_status=READY_FOR_REVIEW`, `next_actor=GPT-Planner`, and stop.
