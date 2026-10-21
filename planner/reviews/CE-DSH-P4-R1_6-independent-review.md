# CE-DSH-P4-R1.6 — GPT Planner Independent Review

- Current remote `main`: `b35e6dcc5c966b75df99d72b6a9621aed09528a1`
- R1.6 implementation/test commit: `ff64acfc4ddfc97c65f65ca6c7575e7440ea051f`
- Follow-up docs/status commit: `b35e6dcc5c966b75df99d72b6a9621aed09528a1`
- Decision: **ACCEPTED for offline engineering scope; live readiness remains NOT_READY.**
- Review method: GitHub remote source, tests, status, report, plan, commit and diff inspection. GPT did not independently execute the Windows/Docker suite or the local network diagnostic.

## A. P1-A — Overflow-safe ledger replay: ACCEPTED BY SOURCE REVIEW

The current `_valid_amount` first excludes bool/non-numeric values, rejects negative values, then guards `float(v)` conversion and rejects exceptions or non-finite results. The replay loop catches `ValueError` after `JSONDecodeError`, covering integer-string conversion failures on runtimes that enforce an integer digit limit. The new tests exercise huge RESERVED/SETTLED values, duplicate settlement, restart fail-closed behavior and byte preservation.

The code change addresses the reported `OverflowError` path. The executor reports 7/7 R1.6 tests, 574/574 full suite, and 151 key tests plus 34 phase4 subset in clean clone. These are **executor-reported results**, not independently rerun by GPT.

## B. P1-B — R1.5 test subgroup count: ACCEPTED

The report/status state the collected count as 42 = 21 output-alias tests + 21 ledger tests. The report includes the stated `pytest tests/test_budget_proxy_r15.py --collect-only -q` output summary. No evidence in the reviewed diff suggests tests were added/removed solely to fit the prose.

## C. P1-C — direct-route diagnostics: ACCEPTED WITH LIMITED SCOPE

The report describes Clash Verge + verge-mihomo, global mode with TUN disabled, no active mihomo/wintun adapter, Windows system proxy configured at loopback, and the proxy's explicit empty `ProxyHandler`. It reports DNS/TCP/TLS only to `api.deepseek.com:443`, zero HTTP bytes, a valid TrustAsia certificate, and no matching deepseek connection in the mihomo log during a window with 109 other logged flows.

This is reasonable evidence for the narrow claim that this diagnostic opener did not traverse mihomo at that time. It is **not** proof that every possible process or future network path bypasses all underlay routing; Sangfor aTrust remains an acknowledged limitation. The underlying raw connection-log excerpt is not committed as a separate artifact, so GPT cannot independently reproduce the route classification from GitHub alone. Keep the claim scoped as `DIRECT_ROUTE_VERIFIED (scoped)`, and keep live readiness NOT_READY.

## D. Final SHA / clean clone

Clean-clone was reported PASS at `ff64acfc4ddfc97c65f65ca6c7575e7440ea051f`, with clone HEAD matching the remote SHA at execution time, 312-row recomputation, 34 phase4 subset tests and 151 key-suite tests. Current HEAD `b35e6dcc5c966b75df99d72b6a9621aed09528a1` is a follow-up commit changing only `status.json` and `planner/executor_report.md`; this limitation is explicitly disclosed.

This is acceptable for the current offline engineering review because the follow-up is docs/status only and live readiness remains NOT_READY. Any later live-readiness decision must use a final-SHA gate on the exact then-current HEAD.

## E. Minor portability issue for R1.7

In `tests/test_budget_proxy_r16.py::test_digit_limit_literal_controlled_corrupt`, the branch using `sys.get_int_max_str_digits()` assumes a positive limit. Python can return `0` when the digit limit is disabled; then the test builds only a 10-digit integer and expects it to be corrupt, which is not guaranteed. Use `limit > 0` for the limit+10 branch; otherwise use the 5000-digit fallback. Add a focused regression for the zero/unlimited case.

## Final decision

**R1.6 accepted for offline engineering. No real DeepSeek API pilot is authorized.** Next phase: R1.7 offline algorithm-fidelity audit and pilot preregistration, including the test portability fix and a more auditable, sanitized route-diagnostic artifact. Do not send real model requests or spend budget.
