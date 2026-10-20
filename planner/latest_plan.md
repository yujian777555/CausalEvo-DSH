# CE-DSH-P4-R1.6 — Direct-Route Readiness Diagnostics & Overflow-Safe Ledger Replay

Planner baseline: `a6e6b6e4490ba56ec67fe694fc307242fc8b1af3`

Independent review: `planner/reviews/CE-DSH-P4-R1_5-independent-review.md`

This phase is diagnostics and offline hardening only. **Real DeepSeek model API calls = 0; spend = ¥0.** Do not run `--live`, send HTTP requests to the DeepSeek API, query account balance, or start a paid pilot.

## 0. Handoff

- Fetch `origin/main`; record the actual full SHA.
- Read this plan, the R1.5 independent review, `status.json`, `planner/executor_report.md`, and the R1.5 remediation report.
- Preserve all uncommitted work; do not force-reset or force-push.
- Keep the 312-row Phase 4 live dataset and previously tracked frozen evidence unchanged.
- R1.5 is accepted for offline engineering; this is a new readiness gate, not permission for live calls.

## P1-A — Make corrupted-ledger numeric parsing fail closed without uncaught exceptions

File: `src/causalevo/eval/budget_proxy.py`

Current risk: `_valid_amount` calls `math.isfinite(v)` for arbitrary Python integers. Extremely large integers may raise `OverflowError` during conversion to float. Also, `json.loads` may raise `ValueError` on integer literals exceeding Python's configured digit limit, while the replay loop currently catches only `JSONDecodeError`.

Requirements:
1. Make amount validation total: for any JSON-decoded value, it must return valid/invalid without leaking `OverflowError`, `ValueError`, or `TypeError`.
2. Require non-bool numeric values, finite representability for the ledger's actual float accounting, and nonnegative amounts. If conversion to the accounting representation fails or becomes non-finite, reject the amount.
3. Catch numeric parser failures during ledger replay and mark `ledger_corrupt=true`, set the gate stopped, and refuse all requests. Do not silently skip the line.
4. Never append auto-repair records to a corrupt ledger.
5. Preserve the original corrupt ledger bytes for audit.
6. Add regression fixtures for:
   - `reserved_cny = 10**400` (or equivalent JSON numeric literal)
   - `cost_cny = 10**400`
   - a JSON integer literal exceeding the runtime's configured digit limit, if the runtime enforces one
   - normal finite integer and float amounts
   - NaN, Infinity, bool and negative amounts
7. Verify malformed ledgers result in a controlled corrupt/stopped state, not an unhandled exception. Confirm new requests are refused and restart remains fail-closed.
8. Do not change ordinary valid accounting or historical ledger semantics.

## P1-B — Correct R1.5 test-category counts

- Inspect the actual collected cases in `tests/test_budget_proxy_r15.py`.
- Current source appears to contain 21 output-alias cases (18 parameterized + 3 standalone) and 21 ledger cases, total 42.
- Update `docs/PHASE4_R1_5_REMEDIATION.md`, `planner/executor_report.md`, and `status.json` to reflect the verified collection. Preserve the correct overall full-suite result and do not add/remove tests merely to match prose.
- Run collection output (e.g. `pytest --collect-only`) and include the exact command and result.

## P1-C — Verify actual direct egress path without an API request

Purpose: investigate the existing `DIRECT_ROUTE_UNVERIFIED` condition. Do not send an HTTP request or any model prompt to DeepSeek.

Required diagnostics:
1. Identify the actual Windows global proxy/TUN software, version, active mode, and configuration source from the environment. Do not guess the software.
2. Record relevant environment proxy variables and application proxy settings without printing credentials or tokens.
3. Confirm the Python direct opener disables HTTP(S) proxy-environment handling, and confirm the Proxy upstream URL is fixed to the allowlisted `https://api.deepseek.com` endpoint.
4. Inspect the actual TUN routing rule and connection/log evidence for `api.deepseek.com:443`. The goal is to prove the connection is classified as DIRECT, not merely that Python has no proxy environment variables.
5. If the software provides reliable connection/rule logs, perform a TCP connect and TLS handshake to `api.deepseek.com:443` only; send **no HTTP request**, no API key and no request body. Record DNS result, handshake result, route classification and timestamps. Redact local IPs if not needed.
6. Do not disable or reconfigure the user's global proxy without explicit authorization.
7. Do not call `/models`, `/user/balance`, `/chat/completions`, or any HTTP/API endpoint. A TCP/TLS diagnostic must terminate immediately after the handshake.
8. If system-level TUN route classification cannot be independently proven, record `DIRECT_ROUTE_UNVERIFIED`; do not claim success based only on environment variables or a successful TLS handshake.
9. A successful direct-route diagnostic does not itself authorize a live model call. A separate explicit budget authorization and Planner approval are still required.

## P1-D — Final-SHA verification and evidence integrity

- Run full tests after code and test changes.
- Push all code/tests/reports first.
- Record full `git ls-remote origin main` SHA and verify local HEAD matches it.
- Run clean-clone against that exact final SHA, including the R1.5 and new R1.6 regression suites, seven key suites, phase4 subset and 312-row recomputation.
- Do not make further commits after the final Gate. If a necessary docs-only commit follows, explicitly mark it as not covered and rerun the Gate before any live-readiness decision.
- Verify historical Phase 4 live data SHA and frozen artifact provenance remain unchanged.

## Validation matrix

1. New overflow-safe ledger tests.
2. Existing `tests/test_budget_proxy.py`, `tests/test_budget_proxy_r14.py`, `tests/test_budget_proxy_r15.py`.
3. Credential isolation, Proxy E2E and control tests.
4. CEA adapter and v2 fake-provider smoke tests.
5. Full `pytest tests/ -q`.
6. Clean-clone tests on the exact final SHA.
7. Direct-route diagnostic evidence (TCP/TLS only; no HTTP).
8. Freeze/data hash audit, key scan, final Git synchronization.

No test may be skipped or weakened to manufacture a PASS. If Docker is unavailable, mark Docker gates NOT_VERIFIED.

## Stop conditions

- If ledger corruption handling is not robust, set `phase_status=BLOCKED`.
- If the direct egress route is not proven DIRECT, keep `DIRECT_ROUTE_UNVERIFIED`; set live readiness to NOT_READY and keep all live API flags disabled.
- If every offline gate passes but direct routing remains unverified, phase may be `READY_FOR_REVIEW` for diagnostics, but it is **not live-ready**.
- New live DeepSeek API calls = 0; spend = ¥0.
- No paid pilot and no Phase 5.
- Push the result, verify final SHA and clean working tree, then stop for GPT Planner review.
