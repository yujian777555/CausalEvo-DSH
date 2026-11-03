# CE-DSH-P4-R1.12-REVIEW-FIX4 — Close remaining independent-review findings

Reviewed Executor delivery: CE-DSH-P4-R1.12-REVIEW-FIX3
Planner review: planner/reviews/CE-DSH-P4-R1_12-review-fix3-independent-review.md
Planner decision: **REQUEST_CHANGES**
Current main at review start: ddbb1f82498c4e7bce4d52eed591e32811e3399b
Next actor: **Kimi-Executor**

## 0. Absolute boundaries

This is an offline-only remediation.

- Additional DeepSeek API calls: **0**.
- New spend: **CNY 0**.
- Do not run live pilot/canary or query account balance.
- Do not enter Phase 5.
- Do not modify R1.12 raw tasks.jsonl, events.jsonl or proxy-ledger/ledger.jsonl.
- Do not modify Phase 0–3 or historical R1.9 frozen data.
- Preserve the current 208-row replication and its statistical definitions.
- Do not claim CEA-v2 improvement, NSGA-III online selection validation or L4 RSI.

Fetch the latest origin/main before starting. The SHA above is the Planner review baseline, not a permanent assumption.

## 1. Task A — Repair symlink test cleanup and make Linux proof reproducible

Files:
- tests/test_r12_hashes.py
- scripts/symlink_escape_check.py
- remove root tmp-symlink-check.py

Findings:
1. In test_symlink_escape_rejected_if_supported, link_dir.mkdir() may succeed and link.symlink_to() may then fail. pytest.skip currently occurs before the later finally block, leaving the directory behind. A subsequent run can hit FileExistsError and be incorrectly skipped.
2. The test uses a fixed directory name, making stale-state and parallel-run collisions possible.
3. scripts/symlink_escape_check.py assumes the symlink already exists; it does not create or clean it.
4. tmp-symlink-check.py is byte-identical to scripts/symlink_escape_check.py and has no distinct documented purpose.

Requirements:
- Create a unique temporary directory beneath the actual allowed root results/phase4/live2/.
- Put all creation and verification inside a cleanup-protected try/finally. If symlink creation is denied, remove the directory before skipping.
- Catch/skip only a genuine unsupported/permission failure for symlink creation; do not convert stale-directory or unrelated errors into skips.
- Point the link to a real file outside the allowed root, such as repository status.json.
- Invoke scripts/verify_r12_hashes.py using a manifest whose pilot_tasks path points to the symlink.
- Assert non-zero exit and the specific 'escapes allowed artifact root' error.
- Make the standalone Linux/WSL script self-contained or remove it if the pytest test is sufficient. It must not rely on a symlink left by another test.
- Remove tmp-symlink-check.py.
- Run the focused test in a symlink-capable Linux/WSL environment and provide exact command, output and exit code. A Windows skip remains a skip, not a pass.

Acceptance:
- Successful symlink-capable execution actually creates the symlink, invokes the verifier, observes rejection and cleans up.
- A denied symlink creation leaves no temporary directory behind.
- Repeated runs do not fail due to stale paths.

## 2. Task B — Strengthen the Holm regression tests

Files:
- tests/test_holm_mapping.py
- scripts/analyze_r12_replication.py only if a small refactor is needed

Findings:
- The fixture in test_old_lexical_assignment_would_be_wrong has raw-p order identical to lexical key order (comparison_a=.01, comparison_m=.04, comparison_z=.20). The old lexical assignment would pass this test, despite its name and comment.
- test_analyzer_applies_holm_only_to_secondary_and_primary_unadjusted reads the committed analysis.json rather than exercising the production analyzer integration. It can pass after the production code regresses if the artifact is not regenerated.

Requirements:
- Change the negative-control fixture so raw-p order and lexical key order differ. Assert explicitly that they differ before checking mapping.
- Demonstrate that a deliberately lexical-key assignment would misassign at least one adjusted value, while holm_adjusted_by_key returns the correct value for each original comparison key.
- Keep the existing distinct-p helper fixture, tie handling, cumulative maximum, monotonicity and [0,1] checks.
- Make the integration test execute production logic. Prefer extracting a small pure function that receives the primary key and secondary comparison raw p-values, applies Holm only to the three secondary keys and returns the adjusted mapping. Alternatively run a deterministic analyzer fixture. Do not rely only on a committed analysis.json snapshot.
- Assert that the primary CEA-v2-online vs B1-random remains unadjusted and the three preregistered secondary comparisons are adjusted.
- Do not change raw p-values, experiment rows, preregistration or scientific conclusions.

Acceptance:
- The regression test fails if the old lexical-order mapping is reintroduced.
- The integration test fails if the primary is included in Holm or if the production analyzer stops applying Holm to the secondary family.
- Focused Holm suite passes with exact count.

## 3. Task C — Explain or remove the newly committed smoke artifacts

Files:
- results/phase4/cea_v2_agent_smoke/run-20261028T125616Z/controller_state.json
- results/phase4/cea_v2_agent_smoke/run-20261028T125616Z/manifest.json
- planner/executor_report.md

The committed manifest describes an adapter_integration_smoke with fake provider, repo_head_sha c007b5c64280bad53c5c6f272be961eca472e855 and recorded_utc 2026-10-28T12:57:51Z. These artifacts were added in the FIX3 implementation commit but are not explained in the FIX3 report.

Requirements:
- State the command/workflow that generated them, the exact source revision, their purpose and whether they are required for a test.
- Verify and record SHA-256 values for both files.
- Scan for credentials, raw provider request bodies, prompts, session logs or other sensitive material.
- Clearly classify them as fake-provider mechanism smoke only, not real-model efficacy.
- If provenance cannot be established or the artifacts are unrelated/redundant, remove them rather than retaining unexplained results.
- Do not modify frozen experiment datasets.

Acceptance:
- Both artifacts have traceable provenance and documented scope, or are removed with the dependent references/tests updated.

## 4. Task D — Normalize active status and executor report

Files:
- status.json
- planner/executor_report.md
- planner/latest_plan.md is this plan; do not overwrite it with a stale FIX3 plan.

Findings:
- Current status says READY_FOR_REVIEW / GPT-Planner / no blockers while planner_review and nested phase4_r1_12.planner_review still record FIX2 REQUEST_CHANGES.
- Active test categories retain stale MISSING_REQUIRED_HASHES, old Holm REQUEST_CHANGES and old missing-task-manifest blocker text even though FIX3 claims those were fixed.
- Current remote SHA fields do not consistently identify ddbb1f8.
- The report's exact clean-clone output is for b9c9499, not current main.

Requirements:
- Preserve old review decisions as history, explicitly labelled historical/superseded.
- Normalize active fields so there is one coherent state: current plan FIX4, current review FIX3 REQUEST_CHANGES, next_actor Kimi-Executor, blockers listing all open FIX4 items.
- Set the active test result to the actual Executor-reported 665 passed / 0 failed / 1 skipped; keep planner_reran=false.
- Distinguish full-suite count from clean-clone key-suite subset count.
- Update current_remote_head and reviewed head to the actual current branch SHA when the record is committed; do not invent the future commit SHA.
- Record clean-clone as PASS only for the SHA actually tested. The report currently supports only b9c9499; 5cbda42 and ddbb1f8 came after it.
- Do not claim Planner independently ran pytest, clean-clone or the 12 SHA checks.

Acceptance:
- No active status field contradicts another.
- Old FIX1/FIX2 findings remain in history, not active categories.
- The report clearly separates Planner-reviewed source observations from Executor-reported runtime/test evidence.

## 5. Task E — Final preservation and exact-SHA gate

After Tasks A–D:
1. Run focused symlink, Holm, analysis-determinism and frozen-task-set tests.
2. Run full pytest suite and record actual terminal output, exit code, passed, failed and skipped.
3. Run scripts/verify_r12_hashes.py and verify all 12 required labels.
4. Verify canonical task manifest SHA-256 remains fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483; exactly 26 tasks × seeds 20261027/20261028 × 4 arms = 208 unique keys.
5. Verify raw tasks/events/proxy-ledger bytes and frozen Phase 0–3/R1.9 artifacts remain unchanged.
6. Verify the existing ledger totals from committed evidence; do not issue new provider requests.
7. Finish all code, tests, docs, report and status edits before committing.
8. Commit and push. Verify local HEAD equals git ls-remote origin main and worktree is clean.
9. Run python scripts/clean_clone_check.py <EXACT_FINAL_ORIGIN_MAIN_SHA> against the exact current remote main SHA.
10. Do not commit or edit any tracked file after that gate. If anything changes after the gate, rerun it against the new exact final SHA.
11. Return the exact SHA, command, raw output, exit code and whether the symlink case was passed or skipped.

The repository status/report must not claim that a gate ran on a SHA that it did not test. The exact gate result may be returned in the Executor completion message; do not create a post-gate docs commit just to record it.

## 6. Stop conditions and final Executor response

Stop immediately if:
- Any frozen raw data changes.
- Any credential or sensitive provider content is found.
- A test failure or unexplained skip occurs.
- Hash verification or task coverage fails.
- Budget/accounting state suggests a new API request would be needed.

Final response must include:
1. Changed files and reasons.
2. Symlink test exact command/output/exit code on Linux/WSL; Windows skip reason if applicable.
3. Holm helper and production-integration tests, including negative-control proof.
4. Smoke artifact provenance decision and SHA-256/security scan.
5. Full-suite exact output, including skipped count and exit code.
6. 12-label hash verification and 208-row coverage result.
7. Frozen-data preservation results.
8. Exact final origin/main SHA, local/remote equality and clean worktree.
9. Exact-SHA clean-clone command/output/exit code.
10. New API calls = 0; new spend = CNY 0; no balance query.
11. Remaining limitations.

After completion, stop and wait for GPT Planner review. Do not start Phase 5.
