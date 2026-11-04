# CE-DSH-P4-R1.12-REVIEW-FIX4 — GPT Planner Independent Review

- Date: 2026-11-04
- Repository: yujian777555/CausalEvo-DSH
- Branch: main
- Executor submission / reviewed SHA: 717a1fbe8371a444c33f02ff9300c90505ec5ea7
- FIX4 takeover baseline: 5d1c12c3d9b709530e6decbaa4bd7289826b2b97
- GitHub refs/heads/main observed during review: 717a1fbe8371a444c33f02ff9300c90505ec5ea7
- Compare: 5d1c12c... -> 717a1fb... is ahead by 1 commit, behind by 0
- Decision: **REQUEST_CHANGES**
- Next actor: Kimi-Executor
- Additional live API calls authorized: **0**
- New spend authorized: **CNY 0**

## 1. Review scope and evidence standard

Planner inspected the GitHub main ref, commit metadata and diff, FIX4 changed-file list, status.json, executor_report.md, symlink test and helper, Holm analyzer and tests, smoke artifacts, reconciled manifest, and clean_clone_check.py.

Changed files in the FIX4 commit:
- planner/executor_report.md
- results/phase4/live2/phase4-r12-replication-pilot-20261027T034229Z/manifest_reconciled.json
- scripts/analyze_r12_replication.py
- scripts/symlink_escape_check.py
- status.json
- tests/test_holm_mapping.py
- tests/test_r12_hashes.py
- tmp-symlink-check.py (deleted)

Evidence boundary:
- GitHub API independently confirms that current main at the time of review points to 717a1fbe8371a444c33f02ff9300c90505ec5ea7.
- The exact-SHA clean-clone output, local HEAD/remote equality, worktree cleanliness, Windows/WSL commands, pytest counts, 12-file hash verification, and ledger recomputation are Executor-reported. Planner did not run them locally.
- GitHub reports zero check-runs for this commit; the supplied test results are local Executor runs, not GitHub Actions results.
- Planner inspected the actual code paths and test assertions; code-level findings below are independently observed.

## 2. Findings

### P2 — Symlink test skips every OSError, not only genuine symlink capability/permission failures

In tests/test_r12_hashes.py, the test now correctly creates a unique temporary directory beneath results/phase4/live2 and puts the link creation, verifier invocation and skip inside a cleanup-protected try/finally. The cleanup defect from FIX3 is fixed.

However, link.symlink_to(...) still catches:
```python
except (OSError, NotImplementedError) as exc:
    pytest.skip(...)
```

This treats every OSError as a platform limitation. It can silently convert unrelated failures (for example, I/O error, no space, missing path or other filesystem corruption) into a skipped test. This does not meet FIX4's explicit requirement to skip only a genuine unsupported/permission failure.

**Required in FIX5:**
- Skip NotImplementedError.
- For OSError, skip only an explicit allowlist of symlink-related permission/unsupported errors (including Windows WinError 1314 and appropriate permission/unsupported errno values).
- Re-raise all other OSError instances so the test fails.
- Add a small classifier regression test: known permission/unsupported errors are classified as unavailable; an unrelated error such as EIO is not skipped.
- Preserve the existing finally cleanup behavior.

### P2 — Holm production wrapper can still apply Holm to the primary if its input is contaminated

The helper-level mapping and negative-control tests are now non-vacuous. The raw-p key order differs from lexical order, and the test explicitly proves that lexical assignment misplaces the adjusted values.

The production wrapper is:
```python
def apply_secondary_holm(primary_key, secondary_raw_p):
    return {primary_key: None, **holm_adjusted_by_key(secondary_raw_p)}
```

Python dictionary expansion means that if primary_key is present in secondary_raw_p, the adjusted mapping overwrites the earlier None. The primary then receives a Holm-adjusted p-value, contrary to the function's docstring/contract.

The current main() separately filters the primary from its secondary list, so the present execution path is correct. But the integration test manually constructs a secondary_raw mapping that already excludes the primary and then asserts that same fixture precondition. It does not protect against a future regression in the production family construction or a contaminated function input.

**Required in FIX5:**
- Make the production API enforce primary exclusion rather than trusting the caller. Preferred design: pass the raw p-value mapping for all comparisons to a pure function, have it preserve the primary as None and Holm-adjust only all other keys, and make main() call that function with the complete comparison mapping.
- Alternatively, reject any input mapping that contains primary_key and test the rejection; however, the preferred all-comparisons API gives stronger regression protection.
- Test with the primary key actually present in the input mapping and assert its returned adjustment is None, while all secondary comparisons receive the correct Holm values.
- Keep the current non-vacuous lexical-order negative control and tie/monotonicity/bounds tests.

### P2 — Exact-SHA clean-clone helper bypasses its remote check when an explicit SHA is supplied

The Executor reports separately checking git ls-remote origin main, and GitHub API independently confirms that refs/heads/main is 717a1fbe8371a444c33f02ff9300c90505ec5ea7. Therefore the reported target SHA matches the GitHub main ref at review time.

However, scripts/clean_clone_check.py contains:
```python
expected = sys.argv[1] if len(sys.argv) > 1 else _remote_sha()
...
git clone --quiet str(REPO) clone
...
CLEAN CLONE OK: HEAD ... == origin/main
```

When the caller supplies the explicit SHA (as in the reported command), _remote_sha() is not called. The script clones the local REPO path, so the clone's origin is the local repository path, not necessarily GitHub origin. Thus this script's own success line does not establish that GitHub origin/main equals the supplied SHA. The separately reported git ls-remote and current GitHub API ref happen to corroborate the SHA for this run, but the reusable gate helper itself is misleading and can false-pass in a future run if a local commit is not pushed.

**Required in FIX5:**
- Always query the configured origin/main SHA, even when an explicit expected SHA is supplied.
- Fail closed if the remote SHA cannot be determined or if the explicit expected SHA differs from remote main.
- Either clone the actual origin URL at main, or explicitly label the operation as a local-source clone after proving that local HEAD and remote main both equal the expected SHA. Do not print that the clone's origin/main was checked if it was not.
- Add a regression test or deterministic helper test for explicit-SHA/remote-SHA mismatch.
- The final gate must again be run against the exact final remote main SHA after all FIX5 changes.

## 3. FIX4 items that are accepted at source-review level

- GitHub main currently points to the submitted SHA 717a1fbe8371a444c33f02ff9300c90505ec5ea7; the compare from the takeover SHA contains one commit and the eight files listed above.
- The symlink pytest test now uses a unique temporary directory under the actual allowed root and cleanup is protected by finally. The standalone Linux/WSL script creates its own unique symlink and temporary manifest, invokes the verifier, asserts the escape rejection, and removes its temporary directory. The duplicate tmp-symlink-check.py is deleted.
- The Holm negative-control fixture is now non-vacuous: raw-p order [z,m,a] differs from lexical order [a,m,z], and the expected adjusted mapping is correct.
- main() currently constructs the three secondary comparisons by excluding the primary comparison key before calling apply_secondary_holm.
- The smoke directory contains exactly manifest.json and controller_state.json. The manifest labels it fake-provider adapter integration smoke, records source revision c007b5c64280bad53c5c6f272be961eca472e855, and explicitly says NOT real-model efficacy. The controller state inspected in this review contains no obvious API-key, prompt, session, or authorization strings. SHA-256 values and the deeper sensitive-content scan remain Executor-reported.
- manifest_reconciled.json updates the analysis_script SHA entry to match the modified analyzer; the other 11 manifest entries are unchanged in the commit diff.

These accepted source observations do not mean FIX4 is accepted as a whole; the three findings above remain open.

## 4. Final-SHA gate and status-file interpretation

The Executor completion message reports:
- local HEAD == git ls-remote origin main == 717a1fbe8371a444c33f02ff9300c90505ec5ea7;
- clean worktree;
- clean-clone command targeted 717a1fbe8371a444c33f02ff9300c90505ec5ea7 and exited 0;
- no post-gate commit.

GitHub API independently confirms refs/heads/main equals that SHA at review time.

status.json intentionally records the clean-clone result as pending at commit time because the plan prohibited post-gate tracked-file changes. The completion message supplies the subsequent result. This is not treated as an active blocker for the submitted FIX4 commit, but the helper implementation weakness described above must be fixed before the next final gate.

## 5. Scientific interpretation — unchanged

R1.12 remains a same-suite fresh-seed replication, not unseen-task generalization. The committed analysis reports:
- B0-original: 0.8846153846
- B1-random: 0.9423076923
- B5-v1-frozen-pareto: 0.9230769231
- CEA-v2-online: 0.9423076923
- Primary CEA-v2-online vs B1-random paired difference: 0
- Exact cluster sign-flip p: 1.0
- Reported 95% CI: [-0.0769230769, 0.0769230769]
- Live NSGA-III parent-selection calls: 0
- Live NSGA-III survivor-selection calls: 0
- Behavioral observations: 5
- L4 RSI: not implemented

There is no evidence of CEA-v2 superiority, no live validation of NSGA-III selection, and no evidence of a reliable learned strategy.

## 6. Decision and next action

**REQUEST_CHANGES.** FIX4 is not accepted yet. Issue CE-DSH-P4-R1.12-REVIEW-FIX5 for the three narrow offline fixes above.

No additional DeepSeek API calls, no new spend, no balance query, no live pilot/canary, no raw R1.12 data edits, no Phase 0–3 or historical R1.9 changes, and no Phase 5.

After FIX5, Executor must rerun focused tests, the full suite, hash and frozen-data checks, and the exact-final-remote-main clean-clone gate. No tracked-file edits or commits after that final gate. Planner will then perform another independent review.
