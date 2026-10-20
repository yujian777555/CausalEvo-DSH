# CE-DSH-P4-R1.4 — GPT Planner Independent Review

- Reviewed remote main HEAD: `d9fbfa2697eb68f760fd3c9c2813376cbda679f8`
- R1.4 implementation commit: `de6b3770a7323e761b500ad6822c8fe27900f52e`
- Clean-clone gate recorded by Executor: `13971ac111ec46d1ffe3964f0661616592ef03ee`
- Decision: **CHANGES_REQUESTED / BLOCKED for live-pilot authorization**
- Review method: GitHub remote tree, commit diff, source, tests, status and report inspection. GPT did not execute the Windows/Docker test suite; Executor-reported counts remain unverified by an independent local rerun.
- Planner made no live DeepSeek API calls; no new API spend.

## Confirmed progress

1. `tests/test_credential_isolation.py` exists in the remote tree, correcting the R1.3 missing-test path.
2. `BudgetProxy.reconcile(scope)` now filters by `_request_scope`; tests cover two scopes, partial reconciliation, restart replay and continued blocking.
3. Proxy upstream-key injection now uses `_docker(extra_env=...)` and bare `-e CE_PROXY_KEY`, not a secret value in Docker argv.
4. R1.4 adds output-limit, reconcile and credential-isolation regression tests.
5. Clean-clone found reproducibility issues and addressed them with canonical LF hashing and publication of a previously ignored sweep artifact. This is useful, but the freeze statement needs to describe the controlled addition accurately.

## P0-A — Output-token alias validation still accepts invalid field types

Source: `src/causalevo/eval/budget_proxy.py`, `_output_limit_problem` / `_validate_output_limit`.

Current code checks `mt != mct` before validating each field independently, then validates only the effective field (`max_tokens` takes precedence when present). Python equality compares unlike types as equal:

- `True == 1`
- `256.0 == 256`

Therefore, requests such as these can pass the current validation when the first field is a valid integer:

```json
{"max_tokens": 1, "max_completion_tokens": true}
{"max_tokens": 256, "max_completion_tokens": 256.0}
```

This contradicts the frozen rule that every supplied output-limit field must be a strict positive integer before alias consistency is evaluated.

Required fix:
- Validate every present field independently; reject bool, float, string, null, missing, non-positive and non-integer values.
- Only after each supplied field independently passes strict validation may the integer values be compared for consistency.
- Keep rejection before reservation and upstream forwarding.
- Add tests for int/bool equal-pair and int/float equal-pair. Assert Fake Provider receive count is zero and no scope budget is consumed.
- Do not coerce values or weaken the rule.

Gate A is **NOT PASS** despite the reported 13 invalid-shape tests.

## P0-B — Duplicate SETTLED ledger validation does not fully fail closed

Source: `src/causalevo/eval/budget_proxy.py`, `_replay`, duplicate `SETTLED` branch.

The current branch checks whether `new` is an int/float and whether `abs(old - new) > 1e-12`. It does not reject bool or require finite/nonnegative values in this duplicate branch.

Consequences:
- `bool` is a subclass of `int`, so `true` can compare equal to numeric cost 1.
- Python's default JSON decoder accepts `NaN`; when `new` is NaN, the difference comparison evaluates false, so a malformed duplicate may be accepted as idempotent instead of marking the ledger corrupt.

Required fix:
- Use shared strict validators for initial and duplicate SETTLED events: reject bool, require numeric, finite and nonnegative cost.
- Apply equivalent strict validation to RESERVED monetary amounts, including duplicates.
- Invalid NaN/Infinity/bool/negative values and conflicting valid costs must mark the ledger corrupt, stop the gate and refuse new requests.
- Add ledger fixtures for duplicate SETTLED NaN, Infinity, bool, negative and ordinary conflicting cost; add RESERVED bool/NaN/Infinity fixtures.
- Preserve valid idempotent duplicates and normal restart recovery.

Gate E is **NOT PASS**; existing tests cover ordinary conflicting numbers but not malformed numeric values.

## P1-C — Test counts disagree

- `status.json` reports **525 passed** for the full suite.
- `planner/executor_report.md` reports **523 passed**.
- This must be reconciled from actual pytest terminal output; do not choose either number by assumption.

## P1-D — Clean-clone SHA evidence is inconsistent

Current final HEAD is `d9fbfa2697eb68f760fd3c9c2813376cbda679f8`. The detailed clean-clone output identifies `13971ac111ec46d1ffe3964f0661616592ef03ee`. The report discloses that a docs-only commit followed without rerunning the gate, but another status note claims the gate ran on the housekeeping HEAD.

Required fix: run clean-clone against the exact current remote HEAD, record the full SHA, clone HEAD, remote SHA and exit status, and make status/report agree. Any later commit must trigger another run or be explicitly marked as not covered.

## P1-E — Frozen-integrity wording is inaccurate

The R1.4 diff adds `results/phase3/replay_sweep/sweep_results.jsonl`, modifies `configs/phase3_artifact_manifest.json`, and changes the adapter/driver for canonical LF hashing. The sweep artifact is described as a previously ignored file published unchanged. That may be justified, but “Phase 0–3 zero diff / untouched” is not literally true for the repository tree.

Required fix:
- Distinguish previously tracked frozen content that was not edited from a previously ignored Phase 3 artifact newly added to version control.
- Record the artifact SHA-256 and, if the original local artifact exists, verify byte identity.
- Explain manifest/adapter/driver changes for clean-clone reproducibility. Do not delete the artifact to restore a misleading zero-diff claim.

## Gate decision

| Gate | Planner decision |
|---|---|
| Output limit, including mixed-type equal aliases | **FAIL** |
| Scope-aware UNKNOWN reconcile | Source/test improvement confirmed; Executor reports PASS; Planner did not rerun |
| Credential-isolation test exists remotely | PASS for file presence; behavior not independently rerun |
| Upstream key absent from Docker argv | Source fix confirmed; Docker E2E reported but not independently rerun |
| Ledger duplicate-event integrity | **FAIL** for non-finite/bool monetary values |
| Full test result consistency | **FAIL: 523 vs 525** |
| Clean-clone at current final SHA | **NOT VERIFIED** (recorded SHA 13971ac differs from current HEAD d9fbfa) |
| Freeze statement | **NEEDS CORRECTION** |
| Live API calls / spend this round | Executor reports 0 / ¥0; no live pilot authorized |

**Final decision: R1.4 is not accepted. Keep live API disabled. Next plan: CE-DSH-P4-R1.5, offline only, zero new DeepSeek calls and ¥0.**
