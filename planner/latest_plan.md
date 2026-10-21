# CE-DSH-P4-R1.8 — Online Evolution Controller & Valid Evaluation Protocol (Offline Only)

Planner baseline: 8286d38d38d6c1812e26225031a85690852f0068

Review: planner/reviews/CE-DSH-P4-R1_7-independent-review.md

**Purpose:** move from a frozen Pareto artifact to a tested runtime feedback/update loop, while correcting the proposed experiment's estimand and execution-path gaps. This phase is algorithm work, not another readiness-only phase.

**Hard boundary:** zero real DeepSeek model API calls; ¥0 new spend. Do not run --live, send HTTP requests to api.deepseek.com, query balance, or execute any proposed pilot. This phase does not implement L4 recursive self-modification; it targets a verifiable online evolutionary update loop (runtime L2/L3).

## 0. Handoff and preservation

1. Fetch origin/main and record the actual full SHA. If it differs from this plan's baseline, inspect the intervening commits and rebase the work conceptually; never force-reset or overwrite remote changes.
2. Read this plan, the R1.7 review, the R1.7 algorithm-fidelity audit, the R1.7 pilot proposal, status.json and executor_report.md.
3. Preserve the 312-row historical Phase 4 dataset, all Phase 0–3 frozen results, existing manifests and prior reports. Do not rewrite or relabel historical rows.
4. Existing microtasks are engineering regression tasks, not unseen paper-evaluation data. Synthetic and tape-based results must be labeled as implementation/mechanism validation, never real-model efficacy.

## Task A — Correct the pilot proposal's status and statistical contract

Create docs/PHASE4_R1_8_EXPERIMENT_PROTOCOL.md and docs/PHASE4_R1_7_PILOT_REVIEW.md. Do not delete or silently rewrite the R1.7 proposal; explicitly supersede its conditional-GO wording for live execution.

Required decisions:

1. **Current live decision = NO-GO.** The frozen-adapter proposal is not authorized and must not be executed in this phase. It does not test RSI and its current endpoint/runner contract is incomplete.
2. Choose and define one primary estimand before inspecting any new outcomes:
   - Preferred default: final_success on every task-seed-arm row as a fixed-denominator binary endpoint. Compare B5-v2/CEA-v2 with B1-random using paired McNemar exact testing and a task-cluster bootstrap interval for the paired success-rate difference.
   - Conditional recovery rate (success after retry among first-attempt failures) is secondary/descriptive unless a common pre-treatment failure set is created and the same frozen attempt-1 state is branched to all compared interventions. If using this latter design, explicitly define the shared failure denominator and pairing.
3. Separate the null-hypothesis test from the minimum practically relevant effect. Specify H0, the effect-size target, confidence interval and a deterministic decision rule; do not use “H1 delta >= 0.10” as if it were the complement of “H0 delta <= 0”.
4. Add a power/sensitivity analysis using plausible discordant-pair rates and task-level clustering. With only 26 task clusters / 52 task-seed pairs, label the study exploratory if it is not adequately powered. Do not promise confirmatory evidence from an underpowered pilot.
5. Freeze the exact task IDs, canonical task-manifest hash, seed list, arm names, code paths and output schema in the protocol before any later experiment. Clearly mark the 26 microtasks as engineering/pilot tasks, not unseen paper test data.
6. Audit the actual per-task RuntimeBudget and BudgetProxy limits in the exact runner. Make every per-task, per-scope, per-run and global cap consistent; test that each cap rejects before forwarding. Do not assume 8 requests per scope unless the runner actually enforces and justifies that envelope.
7. Record the current implementation gap: live_pilot.py still uses CEAV1_BUNDLE for the historical B5 arm; CausalPolicyAdapter.cea_v1_from_manifest is only demonstrated in the fake-provider offline driver. Do not call the proposed B5-v2 arm live-ready until a separately versioned runner is wired and tested offline.
8. Do not produce a new GO decision in R1.8. The protocol must remain “NO-GO pending offline algorithm validation, exact runner integration, and future separate Planner/user authorization”.

## Task B — Implement a bounded online evolutionary controller

Add a new module, preferably src/causalevo/evolution/online_evolution.py, without breaking existing frozen APIs. The exact module name may follow repository conventions, but document the final choice.

The controller must implement an actual state transition from a completed episode to a changed policy/population that affects later action selection. Merely changing a prompt string or choosing among a static front does not satisfy this task.

### B1. Initialization and candidate identity

- Load initial genome candidates from the manifest-pinned Pareto artifact; verify the external manifest before reading candidates.
- Build a runtime population/active archive using unique effective phenotypes, not just genome_id. Do not mutate the pinned artifact.
- Exclude reserved/no-effect genes from the effective phenotype identity and disclose them; do not pretend they increase action diversity.
- Keep a bounded population (default at most 16 active candidates) and deterministic RNG seed.
- New offspring must retain parent lineage and a stable genome/phenotype identity. Prevent duplicate effective phenotypes from silently occupying the whole population.

### B2. Observable context and feedback

- Use only observable, pre-intervention features: failure_type, edited, invalid, tool/error bucket, verification status and other already-available non-sensitive features.
- Never expose CoT, sealed-test content, hidden judge diagnostics or future episodes to the action selector.
- Receive reward only after the independent judge and accounting ledger have settled the episode.
- Use measured outcome and cost, not an LLM self-rating, as reward evidence.
- Treat unknown_cost, budget_stop, transport and protocol failures as infrastructure outcomes: do not assign them as evidence that a genome is behaviorally bad, and do not retry them.

### B3. Selection, update and evolution

Write a short algorithm design in docs/PHASE4_R1_8_ONLINE_EVOLUTION_DESIGN.md before implementation. Specify equations, tie-breaking, defaults and serialization fields.

Minimum functional contract:
- select(context, episode_id) returns selected genome/phenotype, reason, policy version and population version.
- observe(episode_id, context, selected_genome_id, outcome, measured_cost, measured_calls) records one settled observation and updates context-conditioned reward/cost statistics.
- An observation must be applied exactly once; duplicate episode IDs, out-of-order updates and missing/unknown cost fail closed or enter an explicit non-learning state.
- After a bounded number of new observations, perform a real evolutionary step: select parents from the measured archive, crossover/mutate candidates, deduplicate effective phenotypes, and update the active population/archive. The offspring must be eligible for later selection.
- Use multi-objective fitness grounded in observed outcomes, including at least recovery/final success and incremental cost or call count. If robustness is included, define how it is estimated across observed contexts; do not fabricate a per-episode robustness label.
- Use explicit exploration for unmeasured offspring and prevent an unmeasured candidate from being treated as proven optimal.
- Use NSGA-III (or justify a simpler bounded selection for this phase) for the multi-objective population step. If NSGA-III is used, test that all declared objectives affect selection.
- Freeze all update rules and hyperparameters in a versioned config. No hyperparameter tuning on validation/test results.

This is an online evolutionary controller (L2/L3). Do not label it L4 recursive self-improvement: evolution operators and the evaluator remain fixed in R1.8.

## Task C — Deterministic synthetic validation and ablations

Create a new offline driver and versioned result directory, e.g. scripts/run_cea_v2_offline.py and results/phase4/cea_v2_offline/<run_id>/. Do not overwrite run-20261020 or any earlier result.

Build a deterministic synthetic reward environment with at least three predeclared regimes:
1. stationary context-conditioned action rewards;
2. abrupt reward/context shift where the best effective phenotype changes;
3. context-dependent trade-offs between success and cost.

Use fixed seeds and configuration hashes. Compare:
- random intervention;
- fixed rule policy;
- static frozen Pareto selection;
- existing frozen LinUCB snapshot where feasible;
- new online evolutionary controller.

All arms receive the same episode stream and equivalent action/cost envelopes. Use prequential evaluation: select first, then observe only that episode's settled reward, then update for subsequent episodes. No future-row access. Record per-episode selected genome, context, reward vector, cost, policy/population versions, update event, lineage, and cumulative regret.

Report recovery/success, reward, cost/calls, cumulative regret, adaptation lag after regime shifts, effective-phenotype diversity and update counts. Add ablations:
- no online update;
- no mutation/crossover;
- no context features;
- single-objective selection.

These are deterministic mechanism tests only. A synthetic regime designed to favor adaptation is not evidence of real-agent improvement. Include at least one regime where adaptation should not win or where update noise can hurt, so the method is not validated only on favorable cases.

## Task D — Fake-provider integration and invariants

Add a versioned fake-provider/container integration smoke that proves the controller is wired into a real Agent execution path, without external API access.

It must show:
- the selected genome/phenotype actually changes the intervention text passed to the retry attempt;
- judge outcome and settled accounting are fed back after the episode;
- a subsequent selection can change because of the recorded observation;
- infrastructure failure produces no behavioral reward update and no retry;
- manifest/hash mismatch fails closed;
- replaying the same event log yields the same controller state and selections;
- duplicate/out-of-order observations cannot silently double-update;
- history_up_to excludes future episodes;
- population and event-log size remain bounded;
- no CoT/sealed content appears in state, logs or artifacts.

The fake provider must not be used to claim efficacy. Keep evidence_class explicitly marked as synthetic_mechanism_test or adapter_integration_smoke.

## Task E — Results, audit and status

Create:
- docs/PHASE4_R1_8_ONLINE_EVOLUTION_RESULTS.md
- docs/PHASE4_R1_8_EXPERIMENT_PROTOCOL.md
- docs/PHASE4_R1_8_ONLINE_EVOLUTION_DESIGN.md
- docs/PHASE4_R1_7_PILOT_REVIEW.md
- results/phase4/cea_v2_offline/<run_id>/ manifest, per-episode trace, summary and ablations
- appropriate focused tests.

Update status.json and planner/executor_report.md with the exact implementation SHA, current remote SHA, clean-clone SHA, test counts, preserved hashes, and zero-live-call statement. Remove stale top-level blockers from R1.7 and accurately retain only current unresolved items. Distinguish the implementation commit from any docs-only follow-up commit.

## Task F — Required validation

Run and report actual terminal outputs for:
1. focused online-controller unit tests;
2. existing NSGA-III, genome, population/fitness, controller and bandit regressions;
3. fake-provider/container integration tests;
4. tests proving no future leakage, no duplicate updates and deterministic replay;
5. full pytest tests/ -q;
6. clean-clone on the exact final SHA, including the 312-row reconciliation and key safety suites;
7. frozen Phase 0–3 and historical Phase 4 hash checks;
8. secret scan;
9. local HEAD == git ls-remote origin main and clean working tree.

If Docker is unavailable, mark the relevant gate NOT_VERIFIED. Never report a test as passing unless its command actually ran. If a follow-up commit occurs after the full gate, clearly state that its SHA was not tested and do not claim exact-final-SHA verification.

## Stop conditions

- Any frozen-data change, hidden-data leakage, accounting uncertainty or update-order violation: stop and mark BLOCKED.
- If the online controller cannot demonstrate that settled observations change later selection/population, do not call it an online evolution loop.
- If the method is only a frozen selector or ordinary fixed-rule bandit, state that and revise the design rather than relabeling it evolutionary.
- Real DeepSeek API calls: 0; spend: ¥0.
- Do not run --live; do not execute any pilot; do not enter Phase 5.
- Push the completed offline implementation, tests and artifacts; verify exact remote SHA; stop for GPT Planner review.

Final report must state separately:
1. what actually evolves online;
2. what remains fixed;
3. whether L2/L3 runtime update is implemented and tested;
4. why L4 RSI is still not claimed;
5. whether the revised experiment protocol is statistically coherent;
6. all test/clone/hash evidence and unresolved limitations.

Next actor after completion: GPT-Planner.