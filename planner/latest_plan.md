# CE-DSH-P4-R1.12-REVIEW-FIX3 — Final Offline Audit Closure

Reviewed executor HEAD: `e00630d57104ba7d4700e0c72bd3af4d36c94ae7`
Review: `planner/reviews/CE-DSH-P4-R1_12-review-fix2-independent-review.md`
Decision: **REQUEST CHANGES**.
Next actor: Kimi-Executor.

## Absolute boundary

**Offline only. Zero additional real API calls and zero new spend.** Do not rerun the live pilot or canary, do not query account balance, do not enter Phase 5, and do not modify R1.12 raw tasks/events/proxy ledger or frozen Phase 0–3/R1.9 artifacts.

Fetch latest `origin/main` first, inspect the FIX2 independent review and this plan, and preserve all existing commits. The review commit itself changes main; use the current remote HEAD after these Planner updates as your starting point.

## Task A — Make the symlink regression test genuinely exercise the verifier

File: `tests/test_r12_hashes.py`

The current test creates a symlink under `tmp_path` (normally outside the repository) and then calls `link.relative_to(REPO)`. On a platform where symlink creation succeeds, that raises `ValueError` before the verifier runs. On the reported Windows account, the test is skipped, so the symlink containment behavior remains untested.

- Create the symlink in a temporary directory under the real allowed artifact root, such as `results/phase4/live2/`.
- Point it to a file outside that allowed root (for example, the repository's `status.json`).
- Use the manifest path relative to `REPO`, call the verifier, and assert it rejects the resolved symlink escape.
- Remove the temporary symlink/directory in a `finally` block even on assertion failure.
- Skip only if symlink creation genuinely is unsupported or denied. Do not count a skipped case as passed.
- Keep parent traversal, absolute path, inventory, malformed hash/entry, missing-file and hash-mismatch tests.

Do not weaken the verifier to make the test pass.

## Task B — Make the Holm mapping regression test non-vacuous

File: `tests/test_holm_mapping.py`

The current test contains `assert ordered_keys != sorted(secondary) or True`, which always passes. It also does not assert the raw p-values are distinct or that raw-p ordering actually differs from lexical key ordering.

- Remove the tautological assertion.
- Prefer extracting a small pure helper that accepts a mapping from comparison key to raw p-value and returns the Holm-adjusted p-values by the same keys.
- Test a deterministic fixture with three distinct raw p-values whose lexical key order differs from p-value order, for example 0.20, 0.01, and 0.04. Assert the raw values are distinct, the two orderings differ, and the mathematically correct adjusted values are returned to their original keys.
- Keep an integration test verifying the analyzer applies the helper only to the three preregistered secondary comparisons and leaves the primary `CEA-v2-online vs B1-random` unadjusted.
- Keep deterministic tie handling and cumulative-maximum monotonicity.
- Preserve the current experiment's raw data and statistical definitions.

The production mapping code currently appears correctly keyed; this task is to ensure the regression test actually protects that behavior.

## Task C — Reconcile all test counts and active status fields

Files: `status.json`, `planner/executor_report.md`.

The current records conflict:
- `status.json` says 663 passed / 0 failed / 0 skipped;
- its `count_note` says 668 passed / 0 failed / 0 skipped;
- the Executor report says the full suite had 663 passed / 0 failed / 0 skipped;
- the hash-verifier suite is reported as 9 passed / 1 skipped;
- the final user execution summary reports 663 passed / 0 failed / 1 skipped;
- clean-clone's key suites report 240 passed / 1 skipped.
The active status also still reports `current_remote_head=4349161...` while the current main at the time of review was `e00630d...`, and historical gate text remains mixed into active fields.

Required:
1. Rerun the focused tests and `pytest tests/ -q` after Task A and Task B.
2. Record the exact terminal output, exit code, passed count and skipped count. Do not infer or hand-edit counts.
3. Ensure `status.json` and `planner/executor_report.md` match that exact output. Distinguish full-suite results from clean-clone's key-suite subset.
4. Keep historical notes but mark them clearly historical; update active `current_remote_head`, `reviewed_executor_head`, gate SHA, and gate state only with values that are true at the time recorded.
5. Until the terminal gate passes on the exact final SHA, set `phase_status=CHANGES_REQUESTED` (or an equally explicit non-ready state), `next_actor=Kimi-Executor`, and list these blockers. Do not mark `READY_FOR_REVIEW` prematurely.
6. Do not make any post-gate commit just to record the gate result.

## Task D — Final preservation and exact-SHA gate

1. Verify the canonical task manifest SHA-256 remains `fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`; exactly 26 tasks, seeds `20261027, 20261028`, four arms, 208 unique task/seed/arm keys.
2. Run `scripts/verify_r12_hashes.py` and confirm all 12 required artifacts. Confirm raw tasks/events/proxy ledger bytes and historical frozen artifacts remain unchanged.
3. Reconcile the committed ledger and verify the reported 738 settled requests, CNY 1.0397171982 settled cost and UNKNOWN bound 0 from evidence. Confirm zero new API calls and zero new spend.
4. Finish all code, tests, status/report, manifests and review-state changes before the final gate.
5. Commit and push; confirm local HEAD = `git ls-remote origin main` and the worktree is clean.
6. Run `python scripts/clean_clone_check.py <EXACT_FINAL_ORIGIN_MAIN_SHA>` with the exact SHA just read from current `origin/main`. Confirm the command validates that exact SHA and record the actual output/exit code.
7. **Do not commit or edit any file after the gate.** If any change follows, rerun the gate on the new final SHA. A docs-only commit also invalidates the previous exact-final-SHA claim.

If the gate cannot be run or fails, report that honestly and leave the phase blocked.

## Scientific interpretation and stop boundary

The scientific result is unchanged:
- Primary CEA-v2-online vs B1-random: paired difference 0, unadjusted exact cluster p = 1.0, reported 95% CI [-0.076923, 0.076923].
- No evidence of CEA-v2 superiority.
- Live NSGA-III parent-selection calls = 0 and survivor-selection calls = 0.
- Only five behavioral observations; no claim of a reliable learned selection policy.
- Same-suite fresh-seed replication, not unseen-task generalization.
- L4 RSI is not implemented.

No additional API calls, no balance query, no new pilot, and no Phase 5.

## Required final response

Report changed files; focused and full test outputs with actual skip count; raw-data preservation and 12 hash verification; exact final SHA, remote equality and clean worktree; exact final-SHA clean-clone output and exit code; zero new API calls/spend; remaining limitations. After every gate passes, set `phase_status=READY_FOR_REVIEW`, `next_actor=GPT-Planner`, and stop.
