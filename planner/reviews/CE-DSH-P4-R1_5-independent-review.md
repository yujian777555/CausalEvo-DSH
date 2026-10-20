# CE-DSH-P4-R1.5 — GPT Planner Independent Review

- Reviewed remote `main` HEAD: `a6e6b6e4490ba56ec67fe694fc307242fc8b1af3`
- R1.5 code/test commit: `171e070892228f7cc7a2f8dd6d8f0de5642a25f9`
- Clean-clone-tested SHA: `63e80e894c08a8bb90d5e006d96d5c3cbc740bbb`
- Follow-up commit `a6e6b6e...` changes only `status.json` and `planner/executor_report.md`; it is explicitly disclosed as not covered by a rerun.
- Decision: **R1.5 ACCEPTED for offline engineering scope. This does NOT authorize live API calls or a paid pilot.**
- Review method: GitHub source, tests, status/report, tree and commit inspection. GPT did not independently execute the Windows/Docker test suite.

## R1.5 review findings

### P0-A: accepted
Remote source `src/causalevo/eval/budget_proxy.py` now applies `_strict_positive_int` independently to every present output-limit alias before comparing them. This closes the R1.4 cross-type equality issue (`True == 1`, `256.0 == 256`). The check remains before reservation and upstream forwarding. The reported regression tests exercise the HTTP path and assert zero upstream calls for invalid shapes.

### P0-B: accepted
The same source now uses `_valid_amount` for initial and duplicate RESERVED/SETTLED monetary fields, explicitly rejecting bool, non-finite and negative values. Duplicate valid records are accepted only when consistent. Corrupt ledgers stop requests and are not automatically rewritten. The submitted replay tests cover NaN, Infinity, bool, negative and conflicting duplicate values, plus restart fail-closed and valid-history recovery.

### P1-C: accepted with evidence qualification
`status.json` and `planner/executor_report.md` agree on the latest full-suite result: 567 passed, 0 failed, 0 skipped. The report also discloses an earlier run with one Docker timing failure and the operational timeout adjustment before the successful rerun. GPT did not independently rerun this suite.

Minor report arithmetic correction for the next round: `tests/test_budget_proxy_r15.py` appears to contain 21 output-alias cases (18 parameterized + 3 standalone) and 21 ledger cases (42 total), rather than the report's stated 20 alias + 22 ledger split. The overall 42 test count is consistent; update subgroup counts for precision.

### P1-D: accepted with explicit scope
Clean-clone was executed on `63e80e894c08a8bb90d5e006d96d5c3cbc740bbb`, including the new R1.5 tests and historical 312-row recomputation. Current HEAD is `a6e6b6e4490ba56ec67fe694fc307242fc8b1af3`, a follow-up commit whose diff changes only status/report documentation. The report explicitly states the current docs-only commit itself was not rerun. This meets the plan's permitted disclosure path, but the next final gate must run on the exact final SHA before any live readiness decision.

### P1-E: accepted
The report distinguishes the 312-row Phase 4 historical live data from the newly tracked Phase 3 sweep artifact, provides CRLF/LF hashes and says normalized bytes are identical. The earlier blanket “zero diff” wording is corrected. No evidence in the inspected R1.5 diff indicates that the historical 312-row dataset was rewritten.

## Non-blocking robustness issue for R1.6

`_valid_amount(v)` currently calls `math.isfinite(v)` on any Python int/float. Extremely large JSON integers (e.g. `10**400`) may raise `OverflowError` during float conversion rather than returning `False`. The exception would abort `BudgetProxy` construction rather than set `ledger_corrupt` with a controlled fail-closed state. This still prevents the proxy from serving requests, but it does not meet the desired controlled-corruption diagnostic contract. Also, `json.loads` can raise `ValueError` for an integer literal exceeding Python's configured digit limit; the replay loop currently catches only `JSONDecodeError`. Add defensive handling and regression fixtures before live readiness.

## Current live-readiness blockers

1. **TUN-level direct routing remains `DIRECT_ROUTE_UNVERIFIED`.** R1.5 made no live API request, so it did not prove that `api.deepseek.com:443` bypasses the system-level TUN proxy. An empty Python proxy handler or unset environment variables alone are not sufficient evidence against TUN interception.
2. `docker inspect` may expose Proxy container `Config.Env` to host-privileged users; this remains an acknowledged host trust-boundary limitation.
3. GPT has not independently rerun the submitted test suite.
4. No real-model algorithm-improvement evidence is added by R1.5; all new results are engineering and fake-provider tests.

## Final decision

**R1.5 accepted for offline engineering. No live pilot authorization.** Next: `CE-DSH-P4-R1.6`, focused on overflow-safe corrupted-ledger handling, evidence count correction, and a route-level direct-connect readiness diagnostic that performs no HTTP/API request. If the actual egress path cannot be proven DIRECT, preserve `DIRECT_ROUTE_UNVERIFIED` and keep live calls disabled.
