# CE-DSH-P4-R1.12-REVIEW-FIX2 — GPT Planner Independent Review

- Repository: `yujian777555/CausalEvo-DSH`
- Inspected current `origin/main`: `e00630d57104ba7d4700e0c72bd3af4d36c94ae7`
- Reported code/test commit: `4349161eace78db9988a6add27fae7960e8df943`
- Current main's parent: `4349161eace78db9988a6add27fae7960e8df943`
- Decision: **REQUEST CHANGES — offline-only final audit corrections**
- Additional live API calls authorized: **0**.

## Scope and evidence limits

I inspected the current remote ref, current commit and its diff, `status.json`, `planner/executor_report.md`, the R1.12 hash verifier and analyzer, the new regression tests, the reconciled manifest and the committed analysis output. I did not run local pytest, a clean clone, or independently recompute all 12 SHA-256 values in this review turn. Executor-reported test and clean-clone results are not represented as independently rerun by GPT.

The submitted code appears to fix the original Holm mapping in the production analyzer, and the committed analysis uses a stable repository-relative `run_dir`. However, the required final gate and evidence consistency are not closed.

## Findings

### P1 — The clean-clone gate was followed by a commit, so it is not the exact final-SHA gate

The current remote main is `e00630d57104ba7d4700e0c72bd3af4d36c94ae7`; its parent is `4349161eace78db9988a6add27fae7960e8df943`. The current commit message says it records the REVIEW-FIX2 main SHA and clean-clone PASS for `4349161`, and its diff changes `status.json` and `planner/executor_report.md` after that gate.

The report itself says clean-clone was run at `4349161...`, then a docs/status-only follow-up commit was made. The plan explicitly forbids any commit after the final gate. Consequently, the gate is **not proven for current origin/main**. A docs-only commit still changes the final SHA and violates the stated terminal-gate rule.

Required: finish all status/report/test-count corrections first, push them, verify HEAD equals `git ls-remote origin main`, and run clean-clone against that exact final SHA. Do not commit afterward.

### P1 — The test-count evidence is internally inconsistent

The current `status.json` contains all of the following conflicting records:
- `tests.passed=663`, `failed=0`, `skipped=0`;
- `tests.count_note` says `668 passed / 0 failed / 0 skipped`;
- `tests.current_remote_head` still says `4349161...`, while actual current main is `e00630d...`;
- `tests.final_head_clean_clone_status` still describes an older, unrelated R1.11-era SHA and says the then-reviewed HEAD was untested;
- the R1.12 embedded `clean_clone_final` says PASS at `4349161...`, not current main.

The Executor report says the hash-verifier suite was `9 passed / 1 skipped`, but its full-suite row says `663 passed / 0 failed / 0 skipped`. The user's final execution summary reports `663 passed / 0 failed / 1 skipped`. These cannot all describe the same full-suite run. The clean-clone subset also reports `240 passed, 1 skipped`.

Required: use the actual terminal output from the final run, record one consistent full-suite count and exit code, and reconcile the active status fields with the actual final SHA and actual skip count. Preserve older historical notes, but clearly mark them as historical rather than active state. Do not claim the suite has zero skips if the symlink test was skipped.

### P2 — The symlink-escape regression test does not test the intended path on a symlink-capable platform

In `tests/test_r12_hashes.py`, `test_symlink_escape_rejected_if_supported` creates `link` under `tmp_path / "allowed"`, which is normally outside `REPO`, and then calls `link.relative_to(REPO)`. If symlink creation succeeds, that conversion raises `ValueError` before the verifier is called. On the current Windows account, symlink creation is skipped, so this test has not exercised the verifier's symlink-containment behavior.

Required: create the temporary symlink inside a temporary directory under the actual allowed artifact root (e.g. under `results/phase4/live2/`), point it at a file outside that root, invoke the verifier, and clean it up in a `finally` block. Keep a platform skip only when symlink creation genuinely is not permitted. A supported environment must run the assertion and verify rejection.

### P2 — The second Holm mapping test contains a tautological assertion and does not enforce the promised p-value ordering

In `tests/test_holm_mapping.py`, the final assertion is:

`assert ordered_keys != sorted(secondary) or True`

This always passes. The test does not require the raw p-values to be distinct, nor does it assert that raw-p ordering actually differs from lexical comparison-key ordering. Its current synthetic outcome patterns can produce tied small p-values plus 1.0, so the test may fail to exercise the exact precondition it claims to cover.

The first integration test does appear to use a lexical-vs-p-value ordering difference and can catch the prior mapping bug, but the second test's explicit promise is not enforced. Strengthen the tests so the preconditions are asserted. Prefer extracting a small helper that maps a dictionary of comparison keys to raw p-values into adjusted values, then test a deterministic example such as raw p-values 0.20, 0.01, and 0.04 whose comparison-key order differs from p-value order and whose adjusted values differ. Keep an integration assertion that the primary comparison remains unadjusted and only the three secondary comparisons enter Holm.

### P2 — Active status is marked ready despite the new review blockers

The current status says `phase_status=READY_FOR_REVIEW`, `next_actor=GPT-Planner`, and `blockers=[]`, while the evidence fields are contradictory and the final-SHA gate is not on current main. This is premature. Update the active state to request changes and point to the FIX3 plan until the required checks are complete. Set READY_FOR_REVIEW only after all fixes and the exact-final-SHA gate pass.

## Required next action: CE-DSH-P4-R1.12-REVIEW-FIX3

Offline-only:

1. Fix the symlink regression test so it actually invokes the verifier on a symlink path under an allowed root on platforms where symlinks are supported.
2. Strengthen the Holm mapping tests: remove the tautological assertion; enforce raw-p ordering different from lexical key order and non-identical adjusted values, preferably with a deterministic helper-level fixture.
3. Reconcile `status.json` and `planner/executor_report.md`: one accurate full-suite count including skipped tests, actual exit code, accurate active remote SHA, and an explicit distinction between historical gate SHA and current final SHA.
4. Keep all changes—including the new review state, test report, and final executor report—before the terminal clean-clone gate.
5. Run focused tests, the full suite, the hash verifier, raw-data preservation checks, and the frozen task coverage check. Report actual output only.
6. Commit and push all changes. Verify local HEAD = `git ls-remote origin main` and clean worktree.
7. Run `python scripts/clean_clone_check.py <EXACT_FINAL_ORIGIN_MAIN_SHA>` for that exact current remote SHA.
8. **Make no commit after that gate.** If any edit follows, rerun the gate on the new final SHA.

No live API calls, no balance query, no new pilot, no Phase 5. Do not modify R1.12 raw tasks/events/ledger or Phase 0–3/R1.9 frozen artifacts.

## Scientific conclusion remains unchanged

- Primary CEA-v2-online vs B1-random: paired difference 0, unadjusted exact cluster p = 1.0, reported 95% CI [-0.076923, 0.076923].
- No evidence of CEA-v2 superiority.
- NSGA-III parent and survivor selection calls are both 0 in the live run.
- Five behavioral observations do not establish a reliable learned selection policy.
- Same-suite fresh-seed replication only; no unseen-task generalization claim; L4 RSI is not implemented.

This is a request for final audit corrections, not a request to repeat the live experiment.
