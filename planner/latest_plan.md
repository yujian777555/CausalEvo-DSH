# CE-DSH-P4-R1.12-REVIEW-FIX5-R1 — Remote error handling and final gate

Planner review: `planner/reviews/CE-DSH-P4-R1_12-review-fix5-independent-review.md`
Reviewed Executor SHA: `3238ff5c646e09c8c80fa9f89dde54120476d8c6`
Planner decision: **REQUEST_CHANGES**
Next actor: **Kimi-Executor**

## 0. Scope and hard boundaries

Narrow offline-only follow-up. The three principal FIX5 source fixes passed Planner source review. Do not reopen or redesign them unless a regression is found.

- Additional DeepSeek API calls: **0**.
- New spend: **CNY 0**.
- No balance query, no live pilot/canary, no Phase 5.
- Do not modify R1.12 raw tasks/events/proxy ledger.
- Do not modify Phase 0–3 or historical R1.9 frozen artifacts.
- Preserve experiment rows, raw p-values, preregistration and scientific conclusions.
- Re-read the latest origin/main before work. The most recent Planner metadata SHA known when this plan was refreshed is `e1c465b017e5ebdbabb20d2349db3dc33bfd972c`; this metadata commit itself advances main.

## 1. Task A — Make remote lookup fail closed with the documented exit code

File: `scripts/clean_clone_check.py`

Current `_remote_sha()` catches `CalledProcessError` and `IndexError`, but an `OSError` raised while launching Git (for example `FileNotFoundError`) escapes the helper.

Requirements:
- Catch `OSError` from the remote lookup and return `None`.
- Preserve the existing behavior for non-zero git exit and empty output.
- `main()` must print the generic `REMOTE_UNVERIFIED` message and return exit code 3.
- No temporary directory, clone, venv, install or tests may start after remote lookup failure.
- Do not print remote URLs or exception strings that might contain credentials.

Add deterministic regression tests:
1. Mock the underlying `_git(["ls-remote", ...])` call to raise `FileNotFoundError`; assert `_remote_sha()` returns `None`.
2. Exercise `main()` through that failure; assert return code 3 and no `mkdtemp`/clone/install calls.
3. Retain explicit-SHA mismatch and remote-unknown tests.

## 2. Task B — Handoff and status synchronization

**Planner completed the synchronization in the Planner metadata commits following the FIX5 review.**

Current files to verify before the final gate:
- `planner/latest_plan.md`
- `planner/SESSION_HANDOFF_PROMPT.md`
- `status.json`
- `planner/reviews/CE-DSH-P4-R1_12-review-fix5-independent-review.md`

Do not overwrite these files with stale FIX4/FIX5 state. If any correction is needed, make it before the final gate and rerun the gate on the resulting new SHA.

## 3. Task C — Focused regression and exact-final-SHA gate

After Task A:
1. Run `tests/test_clean_clone_check.py` and relevant symlink/Holm/determinism/frozen-task focused suites.
2. Run `scripts/verify_r12_hashes.py`; confirm all 12 labels and canonical task manifest/208-key coverage.
3. Confirm frozen raw data and Phase 0–3/R1.9 artifacts remain unchanged.
4. Run the full pytest suite if broader behavior changed; otherwise document why the focused suite plus clean-clone critical suite is sufficient.
5. Update `planner/executor_report.md` and `status.json` **before** the final commit if the new test evidence changes their recorded state. Keep Executor and Planner evidence distinct.
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