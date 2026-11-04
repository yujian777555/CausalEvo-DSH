# CE-DSH-P4-R1.12-REVIEW-FIX5 — Close remaining test and gate-helper gaps

Planner review: planner/reviews/CE-DSH-P4-R1_12-review-fix4-independent-review.md
Reviewed Executor SHA: 717a1fbe8371a444c33f02ff9300c90505ec5ea7
Planner decision: **REQUEST_CHANGES**
Next actor: **Kimi-Executor**

## 0. Scope and absolute boundaries

Offline-only narrow remediation.

- Additional DeepSeek API calls: **0**.
- New spend: **CNY 0**.
- No balance query, no live pilot/canary, no Phase 5.
- Do not modify R1.12 raw tasks.jsonl, events.jsonl or proxy-ledger/ledger.jsonl.
- Do not modify Phase 0–3 or historical R1.9 frozen artifacts.
- Preserve the existing experiment rows, raw p-values, preregistration and scientific conclusions.
- Fetch latest origin/main before starting. The reviewed Executor submission SHA is 717a1fbe8371a444c33f02ff9300c90505ec5ea7; Planner review commits follow it, so do not assume that is current main at execution time.

## 1. Task A — Narrow symlink-test skip classification

Files:
- tests/test_r12_hashes.py
- optionally a small helper module if needed

Current source correctly uses a unique temporary directory beneath results/phase4/live2 and a finally block that cleans it after successful verification or skip. However, it catches every OSError from symlink_to and turns it into pytest.skip. This can hide unrelated filesystem failures.

Requirements:
- Keep the unique temporary directory and finally cleanup.
- Treat NotImplementedError as unsupported.
- For OSError, skip only explicit symlink-related permission/unsupported errors:
  - Windows privilege/access errors, including WinError 1314 (and WinError 5 only if confirmed as access denial for symlink creation);
  - POSIX permission errors such as EPERM/EACCES;
  - explicit unsupported-operation errors such as ENOTSUP/EOPNOTSUPP/ENOSYS where available.
- Re-raise unrelated OSError values (e.g. EIO, ENOSPC, ENOENT) so the test fails instead of silently skipping.
- Extract a small pure classifier if helpful, and add deterministic tests showing:
  - known permission/unsupported errors are classified as unavailable;
  - unrelated errors are not classified as unavailable.
- Keep the Linux/WSL standalone symlink verifier working and cleanup-safe.

Acceptance:
- Windows WinError 1314 may remain one skipped test, not a pass.
- Linux/WSL with symlink support actually creates the link, invokes the verifier, observes the escape rejection and cleans up.
- An injected unrelated OSError fails the test rather than producing a skip.

## 2. Task B — Make primary Holm exclusion an enforced production invariant

File:
- scripts/analyze_r12_replication.py
- tests/test_holm_mapping.py

Current helper uses a dictionary expansion that allows primary_key in secondary_raw_p to overwrite None. Current main() filters primary correctly, but the helper and tests do not defend the invariant.

Preferred change:
- Change apply_secondary_holm to accept the raw p-value mapping for ALL comparisons, including the primary.
- The function itself must preserve primary_key as None and Holm-adjust only all other comparison keys.
- main() must pass the full comparison raw-p mapping into this production function; do not pre-filter the primary outside the tested function.
- Optionally require primary_key to exist in the input mapping and raise a clear ValueError if absent.
- Do not allow dictionary expansion to overwrite the primary None.
- Test with the primary key actually present in the raw input and assert:
  - output primary adjustment is exactly None;
  - the primary raw p-value is not included in the Holm family;
  - the three secondary comparisons receive the correct adjusted values.
- Retain the non-vacuous lexical negative control, ties, cumulative maximum, monotonicity and [0,1] checks.

Acceptance:
- The production integration test fails if the primary is accidentally included in Holm.
- The production integration test fails if the secondary family stops being Holm-adjusted.
- Existing Holm tests continue to pass; add regression coverage for primary-key contamination.

## 3. Task C — Harden clean_clone_check.py so explicit SHA cannot bypass remote verification

File:
- scripts/clean_clone_check.py
- add a focused test if practical

Planner source review found:
- When an explicit expected SHA is supplied, current code does not call _remote_sha().
- It clones str(REPO), so the clone's origin is the local repository path, not necessarily GitHub origin.
- The output says it equals origin/main, even though that clone's origin may be the local path.

The FIX4 run itself is corroborated by GitHub API (main pointed to 717a1fbe...) and the Executor separately reports git ls-remote equality. This task hardens the reusable gate to prevent future false passes.

Requirements:
- Always query the configured origin/main SHA, even if the caller supplies an explicit expected SHA.
- Fail closed with a distinct non-zero exit if origin/main cannot be determined.
- If explicit expected SHA differs from the observed origin/main SHA, fail before creating the clone.
- Prefer cloning the actual configured origin URL at branch main. If a local-source clone is intentionally retained, prove local HEAD == remote main == expected before cloning and describe it accurately in the success output; do not claim the clone's own origin/main was queried.
- Check the cloned HEAD equals the exact expected remote SHA.
- Add deterministic test coverage for explicit expected SHA / remote SHA mismatch, ensuring it fails before the expensive install/test steps.
- Do not print a remote URL if it may contain embedded credentials.

Acceptance:
- Supplying an explicit SHA never bypasses remote-main verification.
- A mismatch or unavailable remote fails closed.
- Success output accurately states the remote SHA that was independently checked and the clone source.
- Fresh clone still runs the existing recomputation and key test suites.

## 4. Task D — Final preservation and regression run

After Tasks A–C:
1. Run focused symlink classification/containment tests, Holm tests, clean-clone helper tests, analysis determinism and frozen-task-set tests.
2. Run full pytest suite and record exact output, passed, failed, skipped and exit code.
3. Run scripts/verify_r12_hashes.py and verify all 12 required labels.
4. Verify canonical task manifest SHA-256 remains fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483 and coverage remains 26 tasks × seeds 20261027/20261028 × 4 arms = 208 unique keys.
5. Verify raw R1.12 tasks/events/proxy-ledger bytes and frozen Phase 0–3/R1.9 artifacts remain unchanged.
6. Reconcile the historical 738 settled requests, CNY 1.0397171982 rounded total, UNKNOWN bound 0 without any new provider requests.
7. Keep the FIX4 smoke artifacts classified as fake-provider mechanism-only; no real-model efficacy claim.
8. Update executor_report.md and status.json before final commit. Preserve the exact distinction between Executor-reported and Planner-reviewed evidence.
9. Commit and push all changes. Verify local HEAD == git ls-remote origin main and worktree/staging area are clean.
10. Run the clean-clone check against the exact final origin/main SHA using the hardened helper.
11. Do not edit or commit any tracked file after this final gate. If any tracked file changes, rerun the gate against the new exact final remote main SHA.

## 5. Final Executor response

Return:
- changed files and rationale;
- symlink skip classifier behavior and exact Linux/WSL execution evidence;
- Holm primary-contamination regression and production integration output;
- clean-clone helper remote-SHA mismatch test;
- exact full-suite output and exit code;
- 12-label hash verification and 208-row coverage;
- frozen-data hashes/preservation;
- exact final origin/main SHA, local/remote equality and clean worktree;
- exact clean-clone command, raw output and exit code;
- new API calls = 0; new spend = CNY 0; no balance query;
- remaining limitations.

Stop at Phase 4 R1.12 and wait for GPT Planner review. Do not start Phase 5.
