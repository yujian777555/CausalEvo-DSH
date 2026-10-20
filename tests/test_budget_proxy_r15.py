"""P4-R1.5 regression tests: mixed-type output-token aliases and strict
monetary validation of (duplicate) ledger events. Defect reproduction first —
these FAIL on the R1.4 implementation:
- {"max_tokens": 1, "max_completion_tokens": true} passes (True == 1)
- {"max_tokens": 256, "max_completion_tokens": 256.0} passes (256.0 == 256)
- duplicate SETTLED with NaN passes (abs(nan - x) > tol is False)
- bool amounts pass isinstance(int) checks
All tests drive the REAL HTTP path (Fake Provider receive counter) or the
REAL replay entry (ledger files loaded by BudgetProxy), never helper-only.
"""

import json

import pytest

from causalevo.eval.budget_proxy import BudgetProxy, ProxyConfig
from causalevo.eval.fake_provider import FakeProvider

from test_budget_proxy import _mk, _post


@pytest.fixture
def logp(tmp_path):
    return tmp_path / "ledger.jsonl"


def _body(**kw):
    base = {"model": "deepseek-flash",
            "messages": [{"role": "user", "content": "hi"}]}
    base.update(kw)
    return base


# ---------------------------------------------------------------------------
# P0-A: every supplied output-token field validated independently
# ---------------------------------------------------------------------------

MIXED_TYPE_BYPASS = [
    {"max_tokens": 1, "max_completion_tokens": True},      # True == 1
    {"max_tokens": 256, "max_completion_tokens": 256.0},   # 256.0 == 256
    {"max_tokens": True, "max_completion_tokens": 1},
    {"max_tokens": 256.0, "max_completion_tokens": 256},
]

PER_FIELD_ILLEGAL = [
    # (field, value) — bool / float / str / null / zero / negative per alias
    *[(f, v) for f in ("max_tokens", "max_completion_tokens")
      for v in (True, False, 3.5, "256", None, 0, -7)]
]


@pytest.mark.parametrize("bad", MIXED_TYPE_BYPASS + PER_FIELD_ILLEGAL)
def test_alias_fields_individually_strict(logp, bad):
    kw = dict([bad]) if isinstance(bad, tuple) else bad
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy:
            code, _ = _post(proxy.base_url, body=_body(**kw))
            assert code in (400, 403), f"{bad} must be rejected, got {code}"
            assert up.call_count == 0, f"illegal alias reached upstream: {bad}"
            snap = proxy.snapshot()
            assert snap["per_scope"] == {}, "no scope count consumed"
            assert snap["states"] == {}, "no reservation recorded"
    entries = [json.loads(l) for l in logp.read_text().splitlines() if l.strip()]
    assert all(e.get("state") == "REJECTED" for e in entries), \
        "ledger may only hold rejection audits for illegal input"
    assert any(e.get("reason", "").startswith("output_limit") for e in entries)


def test_alias_pair_valid_equal_ints_passes(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0, worst_case_output_tokens=2048) as proxy:
            assert _post(proxy.base_url, body=_body(
                max_tokens=64, max_completion_tokens=64))[0] == 200
            assert _post(proxy.base_url, body=_body(max_tokens=1))[0] == 200
            assert _post(proxy.base_url,
                         body=_body(max_completion_tokens=2048))[0] == 200, \
                "boundary == cap must pass"
            assert _post(proxy.base_url, body=_body(max_tokens=2049))[0] == 403
            assert up.call_count == 3


def test_alias_pair_conflicting_valid_ints_rejected(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy:
            code, _ = _post(proxy.base_url, body=_body(
                max_tokens=100, max_completion_tokens=200))
            assert code in (400, 403)
            assert up.call_count == 0


def test_both_alias_fields_missing_rejected(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy:
            code, _ = _post(proxy.base_url, body=_body())
            assert code in (400, 403)
            assert up.call_count == 0


# ---------------------------------------------------------------------------
# P0-B: strict monetary validation for initial AND duplicate ledger events
# ---------------------------------------------------------------------------

def _seed(logp, entries):
    logp.write_text("".join(json.dumps(e) + "\n" for e in entries),
                    encoding="utf-8")


def _open(logp):
    return _mk(logp, upstream_base_url="http://127.0.0.1:1",
               max_requests_per_task=10, global_cap_cny=5.0)


def _settled_pair(cost2):
    return [
        {"request_id": "a", "state": "RESERVED", "scope": "s", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 0.001},
        {"request_id": "a", "state": "SETTLED", "cost_cny": cost2},
    ]


@pytest.mark.parametrize("cost2", [float("nan"), float("inf"), True, -0.5, 0.002])
def test_duplicate_settled_malformed_or_conflicting_corrupts(logp, cost2):
    _seed(logp, _settled_pair(cost2))
    with _open(logp) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True, \
            f"duplicate SETTLED cost={cost2!r} must corrupt the ledger"


def test_duplicate_settled_identical_valid_is_idempotent(logp):
    _seed(logp, _settled_pair(0.001))
    with _open(logp) as proxy:
        snap = proxy.snapshot()
        assert snap["ledger_corrupt"] is False
        assert snap["known_cost_cny"] == pytest.approx(0.001), \
            "settled history restored exactly once (never duplicated)"


@pytest.mark.parametrize("bad_cost", [float("nan"), float("inf"), True, -0.001])
def test_initial_settled_malformed_corrupts(logp, bad_cost):
    _seed(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SETTLED", "cost_cny": bad_cost},
    ])
    with _open(logp) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True, \
            f"initial SETTLED cost={bad_cost!r} must corrupt"


@pytest.mark.parametrize("bad_reserved", [True, float("nan"), float("inf"), -0.01])
def test_initial_reserved_malformed_corrupts(logp, bad_reserved):
    _seed(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s",
         "reserved_cny": bad_reserved},
    ])
    with _open(logp) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True, \
            f"RESERVED reserved_cny={bad_reserved!r} must corrupt"


@pytest.mark.parametrize("dup_reserved", [True, float("nan"), float("inf"), -0.01, 0.02])
def test_duplicate_reserved_malformed_or_conflicting_corrupts(logp, dup_reserved):
    _seed(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s", "reserved_cny": 0.01},
        {"request_id": "a", "state": "RESERVED", "scope": "s",
         "reserved_cny": dup_reserved},
    ])
    with _open(logp) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True, \
            f"duplicate RESERVED reserved_cny={dup_reserved!r} must corrupt"


def test_corrupt_ledger_refuses_new_requests_and_stays_closed_after_restart(logp):
    _seed(logp, _settled_pair(float("nan")))
    with _open(logp) as proxy:
        assert proxy.snapshot()["stopped"] is True
        proxy.set_current_scope("s")
        code, _ = _post(proxy.base_url, body=_body(max_tokens=8))
        assert code == 429, "corrupt ledger: no new request may pass"
        # the ledger FILE is evidence: original entries NOT auto-rewritten
        on_disk = [json.loads(l) for l in logp.read_text().splitlines() if l.strip()]
        assert any(e.get("request_id") == "a" and e.get("state") == "SETTLED"
                   for e in on_disk)
    # restart on the same corrupt ledger: still fail-closed
    with _open(logp) as proxy2:
        snap = proxy2.snapshot()
        assert snap["ledger_corrupt"] is True and snap["stopped"] is True
        proxy2.set_current_scope("s")
        assert _post(proxy2.base_url, body=_body(max_tokens=8))[0] == 429
    # the ledger file itself was never modified by the proxies
    lines = [json.loads(l) for l in logp.read_text().splitlines() if l.strip()]
    assert len(lines) == 4, "no auto-repair entries appended to a corrupt ledger"


def test_valid_history_still_replays_and_recovers(logp):
    """Guard: valid ledgers (settled + crash-recovered unknowns + scoped
    reconcile) must keep working after the stricter validators."""
    _seed(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s/A", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 0.004},
        {"request_id": "b", "state": "RESERVED", "scope": "s/B", "reserved_cny": 0.01},
        {"request_id": "b", "state": "SENT"},
        {"control": "manual_reconcile", "scope": "s/B", "cleared": ["b"]},
    ])
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy:
            snap = proxy.snapshot()
            assert snap["ledger_corrupt"] is False
            assert snap["known_cost_cny"] == pytest.approx(0.004)
            assert snap["stopped"] is False, "reconciled unknown stays cleared"
            proxy.set_current_scope("s/A")
            assert _post(proxy.base_url, body=_body(max_tokens=8))[0] == 200
