# CE-DSH-P4-R1.12-REVIEW-FIX3 — GPT Planner Independent Review

- Date: 2026-11-03
- Repository: yujian777555/CausalEvo-DSH
- Branch: main
- Reviewed remote HEAD: ddbb1f82498c4e7bce4d52eed591e32811e3399b
- FIX3 implementation commit: b9c949981c8489ada1a48a8cad43a57a3895115c
- Subsequent commits: 5cbda42a37da955da3ddecfd798edadbd127699e (status/report follow-up); ddbb1f82498c4e7bce4d52eed591e32811e3399b (handoff prompt)
- Decision: **REQUEST_CHANGES**
- Next actor: Kimi-Executor
- Additional live API calls authorized: **0**
- New spend authorized: **CNY 0**

## 1. Review scope and evidence standard

This is a Planner source/Git review based on the current GitHub main branch, commit ancestry, FIX3 source files, tests, manifest, analysis output, status.json, latest_plan.md and executor_report.md.

I independently inspected:
- Current main SHA and its parent/commit history.
- The FIX3 analyzer, hash verifier, Holm tests, symlink tests and Linux helper script.
- The 12-label R1.12 reconciled manifest and committed analysis.json.
- The smoke manifest for cea_v2_agent_smoke.
- Active and nested fields in status.json.

I did **not** run pytest, clean-clone, Linux/WSL commands, or recompute the 12 artifact SHA-256 values in a local checkout. Accordingly:
- Source and Git observations below are Planner-reviewed.
- 665/0/1 tests, Linux/WSL symlink execution, 12/12 hash verification, 208-row coverage and ledger totals remain Executor-reported unless separately stated.
- Reading analysis.json is not the same as recomputing results from raw tasks/events/ledger.

## 2. Findings

### P1 — Exact-final-SHA clean-clone gate is not proven for current main

The Executor report records the clean-clone output at b9c949981c8489ada1a48a8cad43a57a3895115c. The report itself says a housekeeping commit followed the gate. Git history confirms:
- b9c9499 is the FIX3 implementation commit.
- 5cbda42 is a later status/report commit whose parent is b9c9499.
- ddbb1f8 is a still later handoff-prompt commit whose parent is 5cbda42.

Current origin/main is ddbb1f82498c4e7bce4d52eed591e32811e3399b. The exact-final-SHA gate recorded at b9c9499 does not cover 5cbda42 or ddbb1f8. The fact that the later commits are documentation-only does not satisfy the explicit exact-final-SHA rule.

**Required:** after all FIX4 code, tests, status and documentation changes are committed and pushed, run clean-clone against the exact then-current origin/main SHA. Do not commit or edit any tracked file after that gate. Return the exact SHA, command, raw output and exit code to Planner.

### P1 — status.json is internally inconsistent and prematurely ready

The current file has top-level phase_status=READY_FOR_REVIEW, next_actor=GPT-Planner and blockers=[], but:
- planner_review still names the FIX2 REQUEST_CHANGES decision.
- phase4_r1_12.planner_review still points to the FIX2 review.
- phase4_r1_12.clean_clone_final still says the FIX3 exact-final-SHA gate is pending.
- tests.categories.clean_clone refers to an older e1df3bd SHA.
- tests.categories.r12_manifest_hashes still says MISSING_REQUIRED_HASHES.
- tests.categories.r12_holm_analysis and r12_task_manifest_validation still preserve old REQUEST_CHANGES findings as active values.
- tests.current_remote_head and other active SHA fields do not consistently identify ddbb1f8.
- limitations contains obsolete active blockers mixed with current limitations.

The historical entries may remain, but they must be clearly marked historical/superseded. Active fields must describe one coherent current state.

**Required:** set the current state to CHANGES_REQUESTED, next_actor=Kimi-Executor and list the FIX4 blockers. Preserve old reviews in history, but normalize active status and current SHA references.

### P2 — symlink test leaks its temporary directory when symlink creation is denied

In tests/test_r12_hashes.py, link_dir.mkdir() and link.symlink_to(target) are inside the same try/except, but the finally cleanup starts only in a later try block. If mkdir succeeds and symlink_to raises OSError, pytest.skip() occurs before entering the cleanup finally. The empty symlink-test-tmp directory is left behind. A subsequent run can then hit FileExistsError at mkdir and be incorrectly skipped again.

The test also uses a fixed directory name, which is vulnerable to stale state or parallel-run collisions.

**Required:** create a unique temporary directory under the actual allowed artifact root; ensure cleanup runs even when symlink creation fails; skip only for a genuine symlink privilege/platform failure. Run the focused symlink test in Linux/WSL where symlink creation is supported.

### P2 — standalone symlink script is not standalone and a duplicate temporary script was committed

scripts/symlink_escape_check.py assumes that results/phase4/live2/symlink-test-tmp/tasks.jsonl already exists as a symlink. It does not create that symlink or clean it up. The root tmp-symlink-check.py has the exact same blob SHA as scripts/symlink_escape_check.py, so it is a duplicate temporary file.

**Required:** make the supported-platform check self-contained (create a unique symlink under the allowed root, invoke the verifier, assert rejection, and clean up in finally), or remove the helper if the pytest case is sufficient. Remove tmp-symlink-check.py unless a distinct, documented purpose is demonstrated.

### P2 — One Holm negative-control test does not actually exercise the old lexical-order bug

tests/test_holm_mapping.py has a good non-vacuous fixture in test_helper_maps_distinct_pvalues_to_correct_keys: raw-p order differs from lexical key order, and it asserts the correct mapping.

However, test_old_lexical_assignment_would_be_wrong uses:
- comparison_a = 0.01
- comparison_m = 0.04
- comparison_z = 0.20

Both raw-p order and lexical key order are comparison_a, comparison_m, comparison_z. The old lexical-order assignment would therefore produce the same mapping for this fixture. This test is not the claimed negative control.

Also, test_analyzer_applies_holm_only_to_secondary_and_primary_unadjusted reads the committed analysis.json instead of exercising the production integration path. It will not detect a future regression in the analyzer if the committed artifact is left unchanged.

**Required:** correct the negative-control fixture so the two orderings differ, assert the precondition explicitly, and test the production primary/secondary family application by calling an extracted pure function or a deterministic analyzer fixture. Keep the current valid helper-level fixture.

### P2 — Newly committed smoke artifacts need provenance explanation

FIX3 adds results/phase4/cea_v2_agent_smoke/.../controller_state.json and manifest.json. The manifest labels this as adapter_integration_smoke using a fake provider, records repo_head_sha=c007b5c64280bad53c5c6f272be961eca472e855 and timestamp 2026-10-28T12:57:51Z. The artifacts are not explained in the current FIX3 executor report.

This does not prove the artifacts are invalid, but their relationship to FIX3 and their reason for being added in that commit are unclear.

**Required:** document their generation command, provenance, hashes and why they belong in the repository; confirm they contain no credentials or raw prompt/session data. If they are unrelated or redundant, remove them. Do not present them as real-model efficacy evidence.

## 3. What appears correct from source review

- holm_step_down implements the standard sorted-p Holm adjustment with cumulative maximum and clipping to 1.
- holm_adjusted_by_key sorts (raw_p, comparison_key) pairs and maps results back to their original keys.
- The production analyzer excludes the primary CEA-v2-online vs B1-random comparison from the secondary Holm family and sets its holm_adj_p to null.
- The verifier declares an exact 12-label inventory, validates SHA-256 syntax, rejects absolute and parent-traversal paths, resolves paths and checks containment within the allowed artifact root before hashing.
- The symlink test's intended path, when created successfully, points from the allowed results/phase4/live2 root to status.json outside that root.
- The committed analysis artifact reports 208 rows, 26 tasks, two seeds and four arms. These values were read from the committed analysis artifact but were not recomputed from raw rows in this review.

These source observations do not replace running tests or verifying hashes in a clean clone.

## 4. Scientific interpretation — unchanged

The committed analysis reports:
- B0-original: 0.8846153846
- B1-random: 0.9423076923
- B5-v1-frozen-pareto: 0.9230769231
- CEA-v2-online: 0.9423076923

Primary CEA-v2-online vs B1-random:
- paired difference: 0
- exact cluster sign-flip p: 1.0
- reported 95% CI: [-0.0769230769, 0.0769230769]

No evidence of CEA-v2 superiority is present in this replication.

The committed analysis reports one evolve event, zero NSGA-III parent-selection calls, zero NSGA-III survivor-selection calls and five behavioral observations. L4 recursive self-improvement remains unimplemented. This is a same-suite fresh-seed replication, not unseen-task generalization.

## 5. Decision and next action

**REQUEST_CHANGES.** FIX3 is not accepted. The next task is CE-DSH-P4-R1.12-REVIEW-FIX4, offline-only.

No additional DeepSeek calls, no balance query, no new pilot, no raw R1.12 data edits, no changes to Phase 0–3 or historical R1.9 frozen artifacts, and no Phase 5.

The Executor must complete the FIX4 plan, commit and push all changes, then run the exact-final-SHA clean-clone gate. No post-gate commit is permitted. Planner will review the resulting commit and the Executor's exact terminal evidence independently.
