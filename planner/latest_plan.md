# CE-DSH-P4-R1.12-REVIEW-FIX5-R1 — Remote error handling and handoff reconciliation

Planner review: `planner/reviews/CE-DSH-P4-R1_12-review-fix5-independent-review.md`
Reviewed Executor SHA: `3238ff5c646e09c8c80fa9f89dde54120476d8c6`
Planner decision: **REQUEST_CHANGES**
Next actor: **Kimi-Executor**

## 0. Scope and hard boundaries

This is a narrow offline-only follow-up to FIX5. The three principal FIX5 source fixes passed Planner source review; do not reopen or redesign them unless a regression is found.

- Additional DeepSeek API calls: **0**.
- New spend: **CNY 0**.
- No balance query, no live pilot/canary, no Phase 5.
- Do not modify R1.12 raw tasks/events/proxy ledger.
- Do not modify Phase 0–3 or historical R1.9 frozen artifacts.
- Preserve experiment rows, raw p-values, preregistration and scientific conclusions.
- Start from the latest origin/main, not an assumed SHA. At Planner review time it was `3238ff5c646e09c8c80fa9f89dde54120476d8c6`; this Planner metadata commit will advance main.

## 1. Task A — Make remote lookup fail closed with the documented exit code

File: `scripts/clean_clone_check.py`

Current `_remote_sha()` catches `CalledProcessError` and `IndexError`, but an `OSError` raised while launching Git (for example `FileNotFoundError`) escapes the helper.

Requirements:
- Catch `OSError` from the remote lookup and return `None`.
- Preserve the existing behavior for non-zero git exit and empty output.
- `main()` must then print the generic `REMOTE_UNVERIFIED` message and return exit code 3.
- It must not create a temporary directory, clone, create a venv, install dependencies or run tests after the remote lookup fails.
- Do not print remote URLs or exception strings that might contain credentials.

Add deterministic regression tests:
1. Mock the underlying `_git(["ls-remote", ...])` call to raise `FileNotFoundError` (and optionally a generic `OSError`); assert `_remote_sha()` returns `None`.
2. Exercise `main()` through that failure and assert return code 3 and no `mkdtemp`/clone/install calls.
3. Retain the existing explicit-SHA mismatch and remote-unknown tests.

## 2. Task B — Synchronize Planner handoff and status before the final gate

Update these tracked files:
- `planner/latest_plan.md`
- `planner/SESSION_HANDOFF_PROMPT.md`
- `status.json`

They must reflect:
- This follow-up plan ID and the current Planner decision REQUEST_CHANGES.
- FIX5 Executor commit `3238ff5c646e09c8c80fa9f89dde54120476d8c6`.
- GitHub main at the time of this review: `3238ff5c646e09c8c80fa9f89dde54120476d8c6`; the new Planner commit advances it, so the Executor must query main again.
- The three main FIX5 source fixes have passed Planner source review.
- The remaining `_remote_sha()` OSError edge and the handoff/status reconciliation task.
- Executor-reported FIX5 results: focused 46 passed / 1 skipped; full suite 687 passed / 1 skipped; 12-label hashes verified; canonical task manifest and 208 keys; historical ledger figures; final clean-clone PASS for `3238ff5c646e09c8c80fa9f89dde54120476d8c6`.
- Evidence boundary: tests, WSL, hashes, ledger and clean-clone remain Executor-reported; GitHub API independently confirmed the SHA; Planner did not rerun local commands.
- Exact science limitations and authorization boundaries.
- Next actor and exact next actions.

Update `status.json` accurately:
- Set `phase_status` to `CHANGES_REQUESTED` and `next_actor` to `Kimi-Executor`.
- Set latest Executor commit/submission SHA to `3238ff5c646e09c8c80fa9f89dde54120476d8c6`.
- Record the GitHub-observed current remote SHA and the Executor-reported clean-clone result for `3238ff5c646e09c8c80fa9f89dde54120476d8c6`.
- Do not claim Planner reran tests or clean-clone.
- Mark the next final-SHA gate as pending because the upcoming code/docs changes will create a new SHA.

The Executor report already records the FIX5 code/test work. Do not rewrite historical results or present Executor evidence as Planner-verified.

## 3. Task C — Focused regression and final exact-SHA gate

After A and B:
1. Run `tests/test_clean_clone_check.py` and the relevant symlink/Holm/determinism/frozen-task focused suites.
2. Run `scripts/verify_r12_hashes.py`; confirm all 12 labels and canonical task manifest/208-key coverage.
3. Confirm frozen raw data and Phase 0–3/R1.9 artifacts remain unchanged.
4. Run the full pytest suite if any broader behavior changed; otherwise document why the focused suite plus clean-clone critical suite is sufficient.
5. Update `planner/executor_report.md` and `status.json` **before** the final commit, and update the handoff prompt in the same pre-gate change set.
6. Commit and push. Verify local HEAD == `git ls-remote origin main`, worktree/staging clean.
7. Run the hardened clean-clone helper against the exact final origin/main SHA. Capture the actual command, raw output and exit code.
8. **No tracked-file edits or commits after the final gate.** If any tracked file changes, rerun the gate against the new exact final remote-main SHA.

## 4. Scientific conclusions — do not change

R1.12 reported:
- B0-original 0.8846153846
- B1-random 0.9423076923
- B5-v1-frozen-pareto 0.9230769231
- CEA-v2-online 0.9423076923
- Primary CEA-v2 vs B1 paired difference 0; exact cluster sign-flip p=1.0; reported CI [-0.0769230769, 0.0769230769].
- No evidence of CEA-v2 superiority.
- Live NSGA-III parent/survivor selection calls both 0.
- Five behavioral observations only; L4 RSI not implemented.
- Same-suite fresh-seed replication, not unseen-task generalization.

## 5. Authorization

- New DeepSeek API calls = 0.
- New spend = CNY 0.
- No balance query.
- No live pilot/canary.
- No raw R1.12 task/event/ledger edits.
- No Phase 0–3 or historical R1.9 frozen-data edits.
- No Phase 5.

Stop after the final gate and report to GPT Planner. Do not self-accept.