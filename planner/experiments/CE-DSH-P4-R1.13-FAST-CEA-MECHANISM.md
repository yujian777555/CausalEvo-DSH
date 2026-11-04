# R1.13 Fast Experiment: CEA-v2 Mechanism Revalidation and CCP-NSGA3

Status: AUTHORIZED FOR OFFLINE ZERO-COST EXECUTION ONLY.

## Motivation
R1.12 had 5 behavioral observations, one evolve event, and zero NSGA-III parent/survivor calls. The first evolve occurs after 4 observations; with exactly four measured candidates, n_parents=4 and the code passes all candidates without NSGA-III. Observation 5 does not trigger the next evolve. Live NSGA-III selection was therefore not tested.

The offline script still has an obsolete episode-15 structural truncation guard. Current online_evolution.py has a bounded offspring-attempt loop (max_attempts=200) and bounded archive eviction. Add tests for termination, archive cap and deterministic replay before removing the old guard; retain a real watchdog.

## E0: full-horizon offline mechanism test
- 10 deterministic seeds × 4 frozen regimes: stationary contextual, abrupt shift, success-cost tradeoff, IID-noise negative control.
- 7 arms: Random, Rule, Static Pareto, Frozen LinUCB, CEA-v2, CEA-v2-no-variation, CEA-v2-no-update.
- Run full 160/240 episode horizons. Same context stream and outcome envelope across arms within each seed/regime.
- Record completion, success, regret, adaptation lag, cost/calls, phenotype diversity, population size, evolution updates, offspring attempts, NSGA-III parent/survivor counters and replay determinism.
- Save per-seed records and aggregate under results/phase4/r13-offline/.
- E0 is synthetic mechanism evidence only, not real-agent efficacy.

## E1: CCP-NSGA3
Hypothesis: CEA-v2 action scoring is context-conditioned but evolutionary parent fitness is global, mixing incompatible failure contexts.
- Keep CEA-v2 unchanged; implement a separate CCP-NSGA3 version.
- Store per-context n, successes, incremental cost and calls.
- Context fitness: [Beta(1,1) posterior-mean success, -mean incremental cost, -mean incremental calls].
- Run NSGA-III parent selection within a context when at least five distinct candidates have observations in that context; otherwise fall back to CEA-v2.
- Add matched random-parent ablation, identical except seeded uniform parent selection.
- Compare Random, Static Pareto, Frozen LinUCB, CEA-v2, CCP-NSGA3 and CCP-NSGA3-random-parent. Use 10 screening seeds; if promising, freeze and run 30 separate confirmation seeds.
- If CCP-NSGA3 does not beat matched random-parent, report that EC selection has not demonstrated value.

## Authorization
Offline CPU simulation only. DeepSeek calls=0; new spend=CNY 0; no balance query, live pilot/canary or Phase 5. R1.12 CNY 2 budget is spent and cannot be reused. Do not modify R1.12 raw data or Phase 0–3/R1.9 frozen artifacts. Outputs only under results/phase4/r13-offline/. Label synthetic_mechanism_test. Live validation requires separate explicit budget approval.