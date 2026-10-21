# CE-DSH-P4-R1.7 — Algorithm-Fidelity Audit & Pilot Preregistration (Offline Only)

Planner baseline: `b35e6dcc5c966b75df99d72b6a9621aed09528a1`

Independent review: `planner/reviews/CE-DSH-P4-R1_6-independent-review.md`

**Scope:** offline code/evidence audit, test portability fix, and design of a scientifically valid next experiment. **Real DeepSeek model API calls = 0; spend = ¥0.** Do not run `--live`, send HTTP requests to DeepSeek, query balance, or start a pilot.

## 0. Handoff

1. Fetch `origin/main` and record its full SHA.
2. Read this plan, the R1.6 independent review, `status.json`, `planner/executor_report.md`, and `docs/PHASE4_R1_6_REMEDIATION.md`.
3. Preserve uncommitted work; no force-reset or force-push.
4. Keep the 312-row historical Phase 4 live dataset and all previously frozen results unchanged.
5. R1.6 is accepted for offline engineering only. There is no live budget authorization.

## P1-A — Fix digit-limit test portability

File: `tests/test_budget_proxy_r16.py`

The test currently branches on `hasattr(sys, "get_int_max_str_digits")`, then uses `limit + 10`. If the function exists but returns `0` (integer conversion limit disabled), this creates a short valid integer instead of an over-limit fixture.

Requirements:
- If `limit > 0`, construct a JSON integer literal with `limit + 10` digits and verify controlled corruption when the runtime enforces that limit.
- If the function is absent OR `limit == 0`, use a 5000-digit literal so float conversion still overflows and the amount validator must reject it.
- Add a focused test for the zero/unlimited configuration, without globally changing interpreter settings in a way that leaks into other tests.
- Preserve existing assertions: proxy construction does not raise, ledger is corrupt/stopped, requests are refused, restart stays fail-closed, and original ledger bytes are unchanged.
- Do not weaken existing tests.

## P1-B — Produce an auditable, sanitized route-diagnostic artifact

Create a compact artifact such as `results/phase4/route_diagnostics/20261021.json` and update the R1.6 remediation report only if needed.

Include only necessary, non-sensitive facts:
- diagnostic timestamp and timezone;
- proxy application/core and version if verifiably available;
- active mode, TUN setting, system-proxy setting and adapter check;
- direct opener configuration and the fixed HTTPS allowlisted host;
- DNS/TCP/TLS outcome and certificate identity/validity;
- diagnostic interval and mihomo log total-flow count plus matching `api.deepseek.com` count;
- exact method used to determine the route, evidence source identifiers or hashes where safe;
- explicit limitations, including the Sangfor aTrust underlay;
- statement that zero HTTP bytes/API calls were sent and no live authorization is implied.

Do not commit credentials, tokens, raw environment dumps, full local paths, or unrelated browsing history. Do not claim the sanitized summary independently proves anything that is not included in its evidence. Keep the route conclusion scoped: it only describes the observed diagnostic connection at that time.

No new network probe is required if the prior source evidence is no longer available. If evidence cannot be reproduced, downgrade the claim and state that limitation instead of fabricating a replacement.

## P1-C — Audit the actual algorithm fidelity before spending more API budget

Inspect the actual code and artifacts, including where present:
- `src/causalevo/evolution/adapter.py`
- genome representation/mutation/crossover and population modules
- NSGA-III selection and fitness computation
- `results/phase3/replay_sweep/sweep_results.jsonl` and the pinned artifact manifest
- `scripts/run_phase4_v2_offline.py`
- the frozen Phase 4 live rows and `docs/PHASE4_ALGORITHM_FIDELITY_AUDIT.md`

Produce `docs/PHASE4_R1_7_ALGORITHM_FIDELITY.md` that distinguishes, with code references and tests:

1. **Offline search:** where NSGA-III actually evolves/selects a population and computes multi-objective fitness.
2. **Artifact production:** how the Pareto front is generated, versioned and hash-verified.
3. **Runtime selection:** how the deployed adapter chooses a genome/intervention from the frozen front.
4. **Feedback/update:** whether live evaluation outcomes update policy, fitness, genome population or the Pareto front.
5. **Recursive self-improvement:** whether an improved child changes the mechanism that generates/evaluates future descendants, or whether the current implementation is only static failure-conditioned selection.
6. **Baseline fidelity:** distinguish historical B4 proxy-heuristic and B5 Pareto-static-bundle from the later offline adapter integration smoke; do not retroactively relabel the historical 312 rows.
7. **Scientific evidence:** restate the existing Phase 4 paired results and their uncertainty accurately. No claim of algorithm superiority or recursive self-improvement may be made unless the evidence supports it.

Classify each property as `IMPLEMENTED_AND_TESTED`, `IMPLEMENTED_NOT_VALIDATED`, `STATIC_ARTIFACT_ONLY`, or `NOT_IMPLEMENTED`, citing exact source files, functions and tests. If a source or artifact is absent, say so; do not infer implementation from a design document.

The goal is to decide whether a new live pilot would test a meaningful algorithmic change or merely repeat a known negative/non-significant comparison.

## P1-D — Draft, but do not execute, a preregistered pilot proposal

Create `docs/PHASE4_R1_7_PILOT_PROPOSAL.md` with a clear GO/NO-GO recommendation based on the algorithm-fidelity audit.

If a pilot is scientifically justified, specify:
- primary hypothesis and primary endpoint;
- fixed task split, task IDs/hash, seeds and pairing;
- exact arms and their actual implementation paths;
- task/run/request/token/cost ceilings;
- equal-budget rules and how cached tokens are accounted for;
- primary statistical test, confidence interval method, multiplicity policy and effect-size threshold;
- stopping rules for provider failures, unknown cost, budget exhaustion and protocol deviations;
- reproducibility manifest and output schema;
- a budget table with low/base/high estimates derived from existing measured records, clearly marking assumptions;
- a rule that the 312 historical rows remain immutable and cannot be pooled into a new confirmatory run unless the preregistration explicitly justifies it.

If no substantive algorithmic improvement or valid new hypothesis exists, recommend NO-GO and explain what algorithm change must happen before spending more.

**Do not execute the proposed pilot. Do not send any real API calls.** A proposal is not authorization. Any future pilot requires a separate explicit user budget authorization and GPT Planner approval.

## P1-E — Validation and final SHA

Run:
1. New R1.6 digit-limit portability tests.
2. R1.5/R1.6 budget and ledger suites.
3. Credential isolation, proxy E2E/control, CEA adapter and v2 offline tests.
4. Full `pytest tests/ -q`.
5. Clean-clone on the exact final SHA, including 312-row recomputation, phase4 subset and all key safety suites.
6. Frozen-data hash audit and secret scan.
7. Verify final local HEAD equals `git ls-remote origin main`; working tree must be clean.

Do not make further commits after the final gate. If a docs-only follow-up is necessary, explicitly mark the exact SHA that was and was not tested; rerun the gate before any future live-readiness decision.

## Stop conditions

- Any regression or unexpected frozen-data change: `phase_status=BLOCKED`.
- If route evidence is unavailable, do not upgrade the route claim beyond what is actually supported.
- Regardless of the diagnostic result, `live_readiness=NOT_READY` until the user explicitly authorizes a budget and GPT Planner approves a separate live-pilot plan.
- Real DeepSeek API calls = 0; spend = ¥0.
- No live pilot and no Phase 5.
- Push the code/tests/artifacts/reports, verify final SHA and clean working tree, then stop for GPT Planner review.
