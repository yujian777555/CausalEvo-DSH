# CE-DSH-P4-R1.5 — Strict Alias Types, Corrupt-Ledger Numeric Validation & Evidence Reconciliation

Planner baseline: `d9fbfa2697eb68f760fd3c9c2813376cbda679f8`

Independent review: `planner/reviews/CE-DSH-P4-R1_4-independent-review.md`

Offline only. **New live DeepSeek model API calls: 0. New spend: ¥0.** Do not run `--live`, query the live balance, or start Phase 5.

## 0. Handoff and preservation

1. Fetch `origin/main` and confirm the remote SHA.
2. Read this plan, the R1.4 review, `status.json`, `planner/executor_report.md` and `docs/PHASE4_R1_4_REMEDIATION.md`.
3. Preserve uncommitted work; do not force-reset or force-push.
4. Keep historical Phase 0–3 outputs and the 312-row Phase 4 live pilot data immutable. R1.4 added a previously ignored Phase 3 sweep artifact to version control for reproducibility; document that controlled addition honestly rather than claiming the entire Phase 0–3 tree has zero diff.

## P0-A — Strictly validate every supplied output-token field

File: `src/causalevo/eval/budget_proxy.py`

- Validate `max_tokens` and `max_completion_tokens` individually before comparing them.
- For every present field, reject bool, float, string, null, zero, negative and all non-integers. Missing both fields is rejected.
- If both fields are present, both must independently pass strict validation and then their integer values must match exactly.
- Do not rely on Python cross-type equality (`True == 1`, `256.0 == 256`) to establish schema validity.
- Keep validation before reservation and upstream forwarding.
- Add tests for:
  - `max_tokens=1, max_completion_tokens=true`
  - `max_tokens=256, max_completion_tokens=256.0`
  - each alias independently bool/float/string/null/zero/negative
  - conflicting valid integers
  - valid single-field and valid equal-integer alias pair
- For every invalid shape, assert Fake Provider receive count is 0, no request scope count is incremented, and no reservation is recorded.

## P0-B — Fail-closed validation for duplicate monetary ledger events

File: `src/causalevo/eval/budget_proxy.py`

- Introduce shared strict validators for RESERVED `reserved_cny` and SETTLED `cost_cny`.
- Reject bool explicitly; require numeric, finite, nonnegative values on first occurrences and duplicate occurrences.
- Duplicate events are idempotent only if all semantic fields are valid and consistent. NaN/Infinity/bool/negative values and conflicting values must set `ledger_corrupt=true`, stop the gate and refuse new requests.
- Ensure the same strict checks are used by the duplicate SETTLED branch; do not depend only on subtraction/tolerance comparisons.
- Add tests for duplicate SETTLED NaN, Infinity, bool, negative and ordinary conflicting costs; add RESERVED bool/NaN/Infinity fixtures and valid duplicate controls.
- Re-run restart/recovery tests to ensure valid histories still replay correctly.
- Keep ledger evidence intact; never auto-rewrite or silently repair corrupt records.

## P1-C — Reconcile test-count evidence

- Run the exact full-suite command against the current source.
- Save the raw pytest summary as an artifact or quote it exactly in the report.
- Update `status.json` and `planner/executor_report.md` to the same full-suite pass/fail/skip counts.
- Explain the prior mismatch (status says 525; report says 523) using actual test collection and terminal output. Never guess.

## P1-D — Verify clean clone on exact final SHA

- After code fixes and final push, record the complete remote `main` SHA.
- Run `scripts/clean_clone_check.py <full_sha>` or equivalent with an explicit target SHA, and confirm clone HEAD equals that SHA.
- Run recomputation and all seven key suites in the clean clone, preserving actual output and exit code.
- Update all status/report notes so they identify exactly the SHA that passed.
- If a docs-only commit follows, either rerun the Gate at that new SHA or explicitly mark the new commit as not covered; never claim both simultaneously.

## P1-E — Correct frozen-data provenance statement

- Report the newly tracked `results/phase3/replay_sweep/sweep_results.jsonl` as a controlled publication of a previously ignored artifact, not as “zero repository diff”.
- Record its SHA-256 and, if the original local artifact exists, compare byte-for-byte with the source artifact before publication.
- Explain why `configs/phase3_artifact_manifest.json`, `src/causalevo/evolution/adapter.py`, and `scripts/run_phase4_v2_offline.py` changed for canonical LF hashing and clean-clone reproducibility.
- Clearly distinguish:
  1. historical Phase 4 live 312-row dataset and previously tracked frozen files unchanged;
  2. previously untracked/ignored Phase 3 artifact newly added;
  3. reproducibility loader/manifest code changed.
- Keep hashes and provenance auditable; do not rewrite historical experiment outputs.

## Validation and report

Run:
1. New output-alias strictness tests.
2. New ledger numeric-corruption tests.
3. Budget proxy and recovery tests.
4. Credential isolation and Docker E2E.
5. Proxy control and CEA adapter/v2 smoke tests.
6. Full `pytest tests/ -q`.
7. Clean-clone recomputation and seven key suites at the exact final SHA.
8. Frozen-data hash/diff audit.

No test may be skipped or weakened to manufacture a PASS. Docker-unavailable tests must be marked NOT_VERIFIED. Fake-provider evidence remains adapter integration smoke, not real algorithm-improvement evidence.

## Stop conditions

- Any P0 failure: `phase_status=BLOCKED`, `next_actor=GPT-Planner`, and stop after pushing failure evidence.
- All gates pass: `phase_status=READY_FOR_REVIEW`, `next_actor=GPT-Planner`.
- New real DeepSeek calls = 0; spend = ¥0.
- No live pilot and no Phase 5.
- Push to `origin/main`, verify local HEAD == remote HEAD and clean working tree, then stop for Planner review.
