# CE-DSH-P4-R1.12-REVIEW-FIX1 — Offline Audit Closure

Reviewed baseline: `6b9a0a7070d98ce706d37aa1dc0a8b97051c7983`
Review: `planner/reviews/CE-DSH-P4-R1_12-independent-review.md`
Decision: **REQUEST CHANGES**.
Next actor: Kimi-Executor.

## Absolute boundary

**Offline-only. Zero new real API calls and zero new spend. Do not rerun the live experiment, do not query account balance, and do not enter Phase 5.** The R1.12 experiment is complete; this plan fixes reproducibility, analysis correctness and final-SHA evidence only.

## Task A — Add verifiable hashes to the run manifests

The frozen protocol requires the analysis script and output hashes in the R1.12 manifest. The current manifest contains only the controller config hash.

- Add SHA-256 values for the frozen protocol, `scripts/analyze_r12_replication.py`, pilot `tasks.jsonl`, `events.jsonl`, `proxy-ledger/ledger.jsonl`, `controller_state.json`, and `analysis.json`.
- Include canary task/event/ledger artifacts and its manifest hash in the pilot's cross-run provenance or a parent round manifest. Do not self-hash a manifest inside itself.
- Add a deterministic verifier/test that recomputes every listed SHA-256 from the committed bytes and fails on a mismatch.
- Do not rewrite raw task/event/ledger rows. If a manifest must change after adding hash fields, recompute and verify all referenced artifact hashes.

## Task B — Correct the preregistered statistical family

In `scripts/analyze_r12_replication.py`:

- Keep CEA-v2-online vs B1-random as the primary comparison; report its exact p unadjusted and use that p in the primary decision rule.
- Apply Holm only to the three preregistered secondary comparisons.
- Implement proper Holm adjusted p-values with the cumulative maximum over sorted step-down adjusted values.
- Add tests covering a nontrivial p-value ordering, the monotonic adjusted-p invariant, and exclusion of the primary from the secondary correction family.
- Keep the frozen task-cluster estimand, exact sign-flip calculation, bootstrap seed/method and observed raw data unchanged. Do not change analysis after looking for a better outcome.

The present primary exact p is 1.0 and the present conclusion remains “no evidence of improvement.”

## Task C — Enforce the exact frozen benchmark coverage

Strengthen the analyzer to validate against the canonical task manifest, not just the set of task IDs found in the data.

- Require the canonical manifest SHA-256 `fcd9df30d61022fecc76067cabe4d3a78c5e9b85750c61d48aa3a8350e8ba483`.
- Require the exact 26 task IDs, seeds `20261027,20261028`, exact four arms, exactly 208 rows and 208 unique `(task_id, seed, arm)` keys.
- Reject missing entire tasks, unexpected tasks, missing/extra arms, unexpected seeds, duplicate keys and wrong row counts.
- Add regression tests for each rejection case. Confirm the existing 208-row data still passes without modifying it.

## Task D — Normalize status and executor report

- Archive the previous execution plan to `planner/plans/CE-DSH-P4-R1.12-execution.md` if not already archived.
- Update `status.json` to `phase_status=READY_FOR_REVIEW` or an explicit offline-audit state, `next_actor=GPT-Planner` after Executor finishes, and current live readiness as stopped/no-more-live-calls.
- Record the reviewed baseline HEAD `6b9a0a7070d98ce706d37aa1dc0a8b97051c7983`, the reported clean-clone SHA `e1df3bdee14f9a23a7d32638a8a9ba19eba7fed7`, and the fact that current HEAD `6b9a0a7070d98ce706d37aa1dc0a8b97051c7983` has not yet passed the exact-SHA gate.
- Mark the R1.12 replication as completed (208/208), with 637 full-suite passes as Executor-reported, not independently rerun by GPT.
- Preserve historical review/status entries. Do not claim that `6b9a0a7070d98ce706d37aa1dc0a8b97051c7983` has already passed clean-clone.

## Task E — Final verification

1. Verify the immutable R1.11 historical Monte Carlo source and repeated-generation regression tests; do not modify historical estimates or R1.9 data.
2. Run focused tests for analysis, manifest hashes, budget reconciliation and all new regression tests.
3. Run full `pytest tests/ -q`; record exact terminal output.
4. Commit all code/tests/manifests/status/report changes before the final gate. Ensure local HEAD equals `git ls-remote origin main` and the worktree is clean.
5. Run `python scripts/clean_clone_check.py <EXACT_FINAL_ORIGIN_MAIN_SHA>` after the last commit. The exact SHA passed by the command must equal the then-current `origin/main` SHA.
6. **Do not create any commit after the final clean-clone gate.** If any change is made, rerun the gate on the new final SHA. Report the gate result and exact SHA in the Executor's final response rather than making a post-gate “recording” commit.

## Required final response

- Exact task coverage and preserved raw artifact hashes.
- SHA-256 entries added and independently reverified.
- Primary unadjusted exact p, CI and secondary Holm-adjusted p-values.
- Test count and exact final SHA clean-clone output.
- Confirmation of zero additional live API calls/spend.
- Confirm no Phase 5 and no claim of NSGA-III validation.

Stop after this offline closure and return to GPT Planner.
