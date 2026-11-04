# CE-DSH R1.12 closeout + R1.13 offline experiment — FAST TRACK

Current FIX5 Executor SHA: `3238ff5c646e09c8c80fa9f89dde54120476d8c6`
GitHub main at plan creation: `91f530bfc2d11978664c65667063c4910bc21c68` (re-query before work)
Decision: **REQUEST_CHANGES** for one narrow `_remote_sha()` OSError edge.
Next actor: **Kimi-Executor**.

## User priority
User said: **“赶紧进入实验吧，不要太慢了”**. Fix the remaining OSError issue narrowly, then immediately run R1.13-E0 offline simulation. Do not wait for the final clean-clone gate to start offline work.

## A. Close R1.12 with one small fix
- In `scripts/clean_clone_check.py`, catch `OSError` in `_remote_sha()` and return `None`.
- Test `FileNotFoundError`: `main()` returns 3 and no `mkdtemp`, clone, venv or install occurs.
- Preserve current mismatch and `CalledProcessError` behavior.
- Do not reopen passed FIX5 symlink/Holm fixes absent regression.

## B. R1.13-E0: full-horizon offline mechanism test
R1.12 had 5 behavioral observations, one evolve event, and zero NSGA-III parent/survivor calls. The first evolve occurs at observation 4; `n_parents=min(4,len(measured))` therefore passes all four measured candidates without NSGA-III. Observation 5 is insufficient to trigger the next evolve. Thus live NSGA-III selection was not tested.

The current offline script still has an obsolete episode-15 structural truncation guard for an earlier phenotype-exhaustion livelock. Current `online_evolution.py` has `max_attempts=200` and bounded archive eviction. Add regression tests for termination, archive cap and deterministic replay; only then remove the stale pre-emptive guard, retaining a real watchdog.

Run **10 deterministic seeds × 4 frozen regimes × 7 arms**, full horizons:
- Regimes: stationary contextual, abrupt shift, success-cost tradeoff, IID-noise negative control.
- Arms: Random, Rule, Static Pareto, Frozen LinUCB, CEA-v2, CEA-v2 no-variation, CEA-v2 no-update.
- Same contexts and outcome envelope across arms within each seed/regime.
- No reward-table changes after seeing results.
- Output per-seed rows and reproducible aggregate under `results/phase4/r13-offline/`.

Record full-horizon completion, termination, success, regret, adaptation lag, cost/calls, phenotype diversity, population size, generations, offspring attempts, NSGA-III parent/survivor counters and replay determinism. E0 is synthetic mechanism evidence only, not real-agent efficacy.

## C. R1.13-E1: one separate EC variant, only after E0
Hypothesis: action scoring is context-conditioned but current evolutionary parent fitness is global, mixing incompatible failure contexts.

Implement separate **CCP-NSGA3**:
- Store per-context n, successes, incremental cost and calls.
- Context fitness: `[Beta(1,1) posterior-mean success, -mean incremental cost, -mean incremental calls]`.
- For a context, invoke NSGA-III parent selection when at least five distinct candidates have observations in that context; otherwise fall back to unchanged CEA-v2.
- Keep population bounded and infrastructure/unknown-cost fail-closed semantics unchanged.
- Add a matched random-parent ablation identical except seeded uniform parent selection.
- Compare Random, Static Pareto, Frozen LinUCB, CEA-v2, CCP-NSGA3 and CCP-NSGA3-random-parent.
- Use 10 screening seeds; if promising, freeze code/config and run 30 separate confirmation seeds. No tuning on confirmation seeds.
- If CCP-NSGA3 does not beat the matched random-parent arm, report that EC selection has not demonstrated value.

Detailed protocol: `planner/experiments/CE-DSH-P4-R1.13-FAST-CEA-MECHANISM.md`.
Executor prompt: `planner/experiments/CE-DSH-P4-R1.13-EXECUTOR-PROMPT.md`.

## Authorization and immutability
Offline CPU simulation only: authorized. DeepSeek calls=0, new spend=CNY 0, no balance query, no live pilot/canary, no Phase 5. R1.12 CNY 2 budget is spent and cannot be reused. Any live experiment needs separate explicit budget approval.
Do not modify R1.12 raw tasks/events/ledger or Phase 0–3/R1.9 frozen artifacts. New output only under `results/phase4/r13-offline/`. Mark `synthetic_mechanism_test`.

## Final gate
Finish code, tests, results, report, status and handoff before final gate. Commit/push, verify exact remote main and clean worktree, run clean-clone at exact final SHA. No tracked edits after gate. Stop for GPT Planner review; do not self-accept.
