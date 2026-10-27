# CE-DSH-P4-R1.12 — GPT Planner Independent Review

- Repository: `yujian777555/CausalEvo-DSH`
- Reviewed executor HEAD: `6b9a0a7070d98ce706d37aa1dc0a8b97051c7983`
- Reported R1.12 code/data commit: `e1df3bdee14f9a23a7d32638a8a9ba19eba7fed7`
- Current reviewed main HEAD: `6b9a0a7070d98ce706d37aa1dc0a8b97051c7983`
- Decision: **REQUEST CHANGES — offline closure only; no additional live calls authorized.**

## Review method and limits

I independently fetched and inspected the committed R1.12 task rows, event log, canary/pilot proxy ledgers, manifests, analysis JSON, analysis script, protocol and status metadata from GitHub. I independently recomputed task/seed/arm coverage, per-arm success rates, ledger terminal states/cost, and the exact task-cluster sign-flip p-values from the committed task rows.

I did **not** run local pytest or clean-clone in this review environment. The reported 637-pass full suite and clean-clone result remain Executor-reported, not independently executed by GPT.

## Independently verified — PASS

### 1. R1.12 task coverage and success rates

The committed `tasks.jsonl` contains **208 rows and 208 unique `(task_id, seed, arm)` keys**. It has the 26 task IDs `micro-000` through `micro-025`, both seeds `20261027` and `20261028`, and all four registered arms.

Recomputed from the raw rows:

| Arm | Successful rows | Success rate |
|---|---:|---:|
| B0-original | 46/52 | 0.884615 |
| B1-random | 49/52 | 0.942308 |
| B5-v1-frozen-pareto | 48/52 | 0.923077 |
| CEA-v2-online | 49/52 | 0.942308 |

### 2. Exact task-cluster sign-flip tests

I independently rebuilt the paired final-success differences by task, kept both seeds together within each of the 26 task clusters, and recomputed the exact two-sided sign-flip distribution.

| Comparison | Mean paired difference | Exact cluster p |
|---|---:|---:|
| CEA-v2-online vs B1-random | 0.000000 | 1.000000 |
| CEA-v2-online vs B5-v1-frozen-pareto | +0.019231 | 1.000000 |
| CEA-v2-online vs B0-original | +0.057692 | 0.531250 |
| B5-v1-frozen-pareto vs B1-random | -0.019231 | 1.000000 |

The reported success rates, paired differences and exact p-values match my recomputation. The current evidence does **not** support a claim that CEA-v2 improves over random or static Pareto selection. The CEA-v2 vs B0 point estimate is positive but its interval crosses zero and the exact test is not significant.

### 3. Live request and cost ledger

I independently parsed both committed proxy ledgers:

- Pilot: 2,142 ledger transitions, 714 unique request IDs; all 714 terminate in `SETTLED`; settled cost CNY 1.0104908718.
- Canary: 72 ledger transitions, 24 unique request IDs; all 24 terminate in `SETTLED`; settled cost CNY 0.0292263264.
- Combined: **738 settled requests**, CNY **1.0397171982**, zero UNKNOWN reservation bound, zero unsettled request IDs.
- Sum of row-level `provider_calls` is 714 for the main pilot, matching the 714 pilot ledger request IDs.

No cost-cap breach or accounting mismatch was found in these committed records.

### 4. Historical R1.11-FIX1 source

The immutable `previous_monte_carlo_estimates.json` is present and contains the three stated historical records with provenance to commit `2bb9e5c3e6f9ac8c01e9f2529d4939459b055b1e`. The report says the repeated-generation regression tests pass 9/9; this test result remains Executor-reported.

## Findings requiring correction

### P1 — Exact final-SHA clean-clone gate is not satisfied

The executor report records a clean-clone PASS at `e1df3bdee14f9a23a7d32638a8a9ba19eba7fed7`. However, the current main HEAD under review is `6b9a0a7070d98ce706d37aa1dc0a8b97051c7983`, a later commit whose title and diff show updates to `status.json` and `planner/executor_report.md`. The R1.12 protocol explicitly requires the clean-clone check to target the exact final `origin/main` SHA after the last commit.

The fact that the follow-up is docs/status-only does not waive the frozen gate. After all requested offline corrections and the final report/status update are committed, rerun the clean-clone gate against that exact final main SHA. Do not make any further commit after the terminal gate; report its exact SHA and output in the Executor's final response.

### P1 — Required artifact hashes are absent from the R1.12 manifest

The frozen protocol §7 says the analysis script and output hashes must be included in the R1.12 manifest. The current pilot `manifest.json` has a controller-config SHA-256 but no hashes for the analysis script, `analysis.json`, task rows, event log, proxy ledger, or frozen protocol.

Add deterministic SHA-256 entries for at least:
- `docs/PHASE4_R1_12_REPLICATION_PROTOCOL.md`
- `scripts/analyze_r12_replication.py`
- pilot `tasks.jsonl`, `events.jsonl`, `proxy-ledger/ledger.jsonl`, `controller_state.json`, and `analysis.json`
- canary `tasks.jsonl`, `events.jsonl`, `proxy-ledger/ledger.jsonl`, and `manifest.json` where appropriate.

Do not create a self-referential manifest hash. Add a test or verification command that recalculates the listed hashes and rejects mismatches. Preserve raw rows and ledgers byte-for-byte.

### P2 — Holm correction does not match the preregistered comparison family

The protocol defines the CEA-v2.1 vs B1-random comparison as the **primary** comparison and specifies Holm correction for the **three secondary comparisons**. The current `analyze_r12_replication.py` applies `holm_adj_p` across all four comparisons, including the primary. It also computes each adjusted value as `p * (m-rank)` without the cumulative maximum required by the Holm step-down adjusted-p definition.

Fix this by:
1. reporting the primary exact p-value unadjusted and evaluating the preregistered primary criterion with that p-value;
2. applying a correctly monotone Holm adjustment only to the three secondary comparisons;
3. adding tests with nontrivial p-value orderings that catch missing cumulative-max behavior and ensure the primary is not in the secondary family.

The current observed adjusted p-values are all 1.0, so this correction is not expected to change the present scientific conclusion. It is still required for protocol compliance and future correctness.

### P2 — Analysis does not enforce the exact frozen task set / fixed 208-row denominator

The analyzer checks that every *observed* task has both seeds and all expected arms, but it does not require the canonical 26-task ID set or exactly 208 rows. If an entire task and its eight rows were removed, the present validation loop could still accept the remaining complete combinations.

Add explicit validation against the canonical task manifest (including its frozen SHA-256) and assert exactly 26 expected task IDs, the two registered seeds, the exact four-arm set, 208 unique keys, and no unexpected task/arm/seed. Add regression tests for a missing whole task, an unexpected task, an unexpected arm and wrong total row count. The current committed dataset itself passed the independent coverage check.

### P2 — Status metadata still describes the experiment as not yet run

At reviewed HEAD, `status.json` still has `phase_status=READY_FOR_EXECUTION`, `next_actor=Kimi-Executor`, and `live_readiness` says R1.12 is not yet ready. Its test-category entries say R1.12 is not run, and `tests.final_head_clean_clone_status` still describes the pre-R1.12 HEAD. Its `tests.current_remote_head` field says `e1df3bd...` while the actual reviewed main HEAD is `6b9a0a7070d98ce706d37aa1dc0a8b97051c7983`.

Normalize the current state to Phase 4 R1.12 review, record the exact reviewed executor HEAD, report the 637 tests as Executor-reported (not GPT-rerun), distinguish the SHA that was tested from the current SHA that remains untested, and set the next actor/blockers/readiness accurately. Preserve historical phase records rather than overwriting them.

## Algorithm-fidelity interpretation

The committed live event log has one `evolve` event with:
- `nsga3_parent_selection_calls = 0`
- `nsga3_survivor_selection_calls = 0`

The manifest confirms the four measured candidates were directly used as parents, with no overflow. The live run did crossover/mutation/population update, but it did **not** exercise NSGA-III parent or survivor selection. The analysis also records only **5 behavioral observations across 52 CEA rows**. This is a real mechanism-level limitation, not a reason to discard the run or to rerun it until selection fires.

The valid conclusion is narrow: the tested CEA-v2-online implementation did not outperform B1-random on this same-suite fresh-seed replication, and the intended NSGA-III selection mechanism remains empirically unvalidated. Do not claim NSGA-III efficacy, unseen-task generalization, or L4 RSI.

## Decision and stop boundary

**REQUEST CHANGES for offline audit closure.** The underlying 208-row data, the independently recomputed primary/secondary exact p-values, and the live spend ledger are consistent. However, the exact final-SHA gate, required artifact hashes, Holm implementation/protocol alignment, complete task-set validation, and status normalization must be fixed before accepting the R1.12 deliverable.

- No additional real API calls are authorized by this review.
- Do not repeat or extend the live experiment.
- Do not enter Phase 5.
- After offline fixes, run the full test suite and exact-final-SHA clean-clone gate; stop at the Phase 4 boundary.

Next plan: `planner/latest_plan.md`.
