# CE-DSH-P4-R1.12-REVIEW-FIX5 — GPT Planner Independent Review

- Date: 2026-11-04
- Repository: yujian777555/CausalEvo-DSH
- Branch: main
- Executor submission / reviewed SHA: `3238ff5c646e09c8c80fa9f89dde54120476d8c6`
- GitHub `refs/heads/main` independently observed at review time: `3238ff5c646e09c8c80fa9f89dde54120476d8c6`
- Compare from FIX5 takeover `3ae1913fa87a23eebab8e6ec3ff33a31a8448fe5`: ahead by 1, behind by 0
- Decision: **REQUEST_CHANGES**
- Next actor: **Kimi-Executor**
- Additional live API calls authorized: **0**
- New spend authorized: **CNY 0**

## 1. Evidence boundary

Planner independently queried GitHub `refs/heads/main`, compared the FIX5 commit against the recorded takeover SHA, fetched the changed source files, inspected the status/plan/handoff files, and queried commit check-runs.

GitHub reports **0 check-runs** for this commit. Therefore:
- Source-level findings below are Planner-reviewed.
- The reported 687 passed / 1 skipped full suite, 46 passed / 1 skipped focused suite, 12-label hash verification, frozen-data hashes, WSL symlink execution, ledger reconciliation, local/remote equality and exact-SHA clean-clone output are **Executor-reported**.
- Planner did not run pytest, WSL, hash recomputation, ledger recomputation or clean-clone locally.
- GitHub API independently confirms the reported final SHA was the remote `main` at review time; it does not independently confirm the local test output.

## 2. Source review findings

### A. Symlink skip classification — SOURCE REVIEW PASS

Inspected `tests/test_r12_hashes.py`:
- `NotImplementedError` and the explicit permission/unsupported allowlist are classified as unavailable.
- EIO, ENOSPC, ENOENT and other unlisted errors are re-raised by the containment test.
- The unique temporary directory and `finally` cleanup remain.
- The EIO injection test invokes the containment test path and asserts propagation plus cleanup.

Executor-reported runtime evidence remains one Windows WinError 1314 skip and a WSL standalone verifier rejection. The WSL command was not independently run by Planner.

### B. Holm primary exclusion — SOURCE REVIEW PASS

Inspected `scripts/analyze_r12_replication.py` and `tests/test_holm_mapping.py`:
- `apply_secondary_holm` now requires the primary key in the full raw-p mapping.
- It filters the primary internally before applying Holm to secondary comparisons.
- The primary output is `None`; the main analysis path passes all four comparisons.
- The integration test includes primary raw p=0.001, checks the three expected secondary adjustments, changes the primary raw p and checks that secondary values do not change, and tests missing-primary rejection.
- The lexical-order negative control, ties, cumulative maximum, monotonicity and [0,1] checks remain.

### C. Clean-clone remote verification — CORE SOURCE REVIEW PASS; ONE EDGE REMAINS

Inspected `scripts/clean_clone_check.py` and `tests/test_clean_clone_check.py`:
- The helper queries remote main even with an explicit SHA.
- Explicit/remote mismatch returns before temporary directory creation and clone/install.
- It clones the configured origin's `main` branch and checks cloned HEAD against the observed remote SHA.
- Clone subprocess output is captured and failure messages are generic; the remote URL is not printed.
- The seven tests cover mismatch, unknown remote, configured-origin clone, output redaction, critical-suite inclusion, clone failure and cloned-HEAD mismatch before install.

Remaining edge:
- `_remote_sha()` catches `CalledProcessError` and `IndexError`, but not `OSError`. If launching Git fails (for example `FileNotFoundError`), the helper raises rather than returning `None`; `main()` therefore does not return its documented distinct remote-unverified exit code 3.
- This is fail-closed in the sense that it does not continue to clone, but it does not satisfy the helper's documented failure contract. Add an `OSError` catch and a deterministic regression test proving exit 3 before clone/install.

## 3. Repository handoff/status synchronization — NOT ACCEPTED

The FIX5 code commit did not update:
- `planner/SESSION_HANDOFF_PROMPT.md`: it still identifies FIX4 REQUEST_CHANGES as the latest decision and does not describe FIX5's final commit or its current follow-up.
- `planner/latest_plan.md`: it still identifies Kimi as the next actor for the original FIX5 plan and uses the FIX4 reviewed SHA.
- `status.json`: it says `READY_FOR_REVIEW`, but `latest_executor_commit` and `executor_submission_sha` are null; clean-clone is still marked pending even though the completion message reports a PASS.

The decision to avoid post-gate edits was correct. However, the handoff/status files must be updated **before** the next final gate, then that new final SHA must pass clean-clone. Do not edit tracked files after that gate.

## 4. Executor-reported results (not independently rerun)

- Focused tests: 46 passed / 1 skipped, exit 0.
- Full pytest: 687 passed / 1 skipped, exit 0.
- Hash verifier: 12 artifacts verified, exit 0.
- Canonical task manifest: `fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`; 26 tasks × 2 seeds × 4 arms = 208 keys.
- R1.12 raw tasks/events/ledger hashes reported unchanged.
- Historical 738 settled; normalized CNY 1.0397171982; UNKNOWN bound 0.
- Final clean-clone command reportedly passed for `3238ff5c646e09c8c80fa9f89dde54120476d8c6`; output and exit code were supplied in the Executor completion message, not stored as a post-gate tracked-file edit.
- New DeepSeek calls 0; new spend CNY 0; no balance query; no live pilot/canary.

## 5. Scientific interpretation — unchanged

R1.12 remains a same-suite fresh-seed replication, not unseen-task generalization. Reported results remain:
- B0-original: 0.8846153846
- B1-random: 0.9423076923
- B5-v1-frozen-pareto: 0.9230769231
- CEA-v2-online: 0.9423076923
- Primary CEA-v2 vs B1 paired difference: 0
- Exact cluster sign-flip p: 1.0
- Reported 95% CI: [-0.0769230769, 0.0769230769]
- Live NSGA-III parent-selection calls: 0
- Live NSGA-III survivor-selection calls: 0
- Behavioral observations: 5
- L4 RSI: not implemented

There is no evidence of CEA-v2 superiority, live NSGA-III selection, a reliable learned intervention strategy or unseen-task generalization.

## 6. Decision and next action

**REQUEST_CHANGES.** The three main FIX5 source defects are repaired at source-review level. One narrow remote-error handling edge and the explicitly requested handoff/status synchronization remain.

Issue the narrow follow-up plan:
1. Make `_remote_sha()` return `None` on `OSError`; test `main()` returns 3 without creating a temp directory or cloning.
2. Update `planner/latest_plan.md`, `planner/SESSION_HANDOFF_PROMPT.md`, and `status.json` to reflect this review, current SHA, current next actor and the Executor-reported gate evidence.
3. Commit/push all changes, verify remote equality and clean worktree, then run clean-clone against the exact new remote-main SHA.
4. No tracked-file changes after that gate. Return raw command/output/exit code to GPT Planner.

No Phase 5. No additional live API calls or spend.

## 7. Follow-up metadata reconciliation

After this review, Planner committed the updated FIX5-R1 plan, handoff prompt and status in commit `e1c465b017e5ebdbabb20d2349db3dc33bfd972c`, then refreshed status in the subsequent metadata commit. This resolves the stale-handoff/status finding from Section 3. The remaining code blocker is only `_remote_sha()` OSError handling. Because these Planner metadata commits advance `main`, the Executor-reported clean-clone PASS at `3238ff5c646e09c8c80fa9f89dde54120476d8c6` does not cover the current final SHA; rerun the gate after the OSError fix and all pre-gate documentation updates.
