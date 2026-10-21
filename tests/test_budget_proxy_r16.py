"""P4-R1.6 P1-A: overflow-safe ledger replay. Extreme monetary values must
produce a CONTROLLED ledger_corrupt + stopped state — never an uncaught
OverflowError/ValueError aborting proxy construction.

Defect reproduction (R1.5 code): math.isfinite(10**400) raises OverflowError,
so a ledger containing 10**400 as reserved_cny/cost_cny aborts BudgetProxy
__init__ with an unhandled exception instead of a controlled corrupt state.
This runtime (Python 3.10.1) has no int_str_digits limit; the digit-limit
fixture is exercised conditionally for runtimes that enforce one.
"""

import json
import sys

import pytest

from causalevo.eval.fake_provider import FakeProvider

from test_budget_proxy import _mk, _post


@pytest.fixture
def logp(tmp_path):
    return tmp_path / "ledger.jsonl"


def _seed(logp, entries):
    logp.write_text("".join(json.dumps(e) + "\n" for e in entries),
                    encoding="utf-8")


def _body(**kw):
    base = {"model": "deepseek-flash", "max_tokens": 8,
            "messages": [{"role": "user", "content": "hi"}]}
    base.update(kw)
    return base


def _assert_controlled_corrupt(logp):
    """Open a proxy on the seeded ledger: construction must NOT raise; the
    state must be corrupt+stopped; new requests refused; restart stays
    fail-closed; the ledger file bytes remain untouched."""
    before = logp.read_bytes()
    with _mk(logp, upstream_base_url="http://127.0.0.1:1",
             max_requests_per_task=10, global_cap_cny=5.0) as proxy:
        snap = proxy.snapshot()
        assert snap["ledger_corrupt"] is True
        assert snap["stopped"] is True
        proxy.set_current_scope("s")
        code, _ = _post(proxy.base_url, body=_body())
        assert code == 429
    with _mk(logp, upstream_base_url="http://127.0.0.1:1",
             max_requests_per_task=10, global_cap_cny=5.0) as proxy2:
        snap2 = proxy2.snapshot()
        assert snap2["ledger_corrupt"] is True and snap2["stopped"] is True
        proxy2.set_current_scope("s")
        assert _post(proxy2.base_url, body=_body())[0] == 429
    assert logp.read_bytes() == before, \
        "corrupt ledger bytes must be preserved for audit (no auto-repair)"


def test_reserved_huge_int_10pow400_controlled_corrupt(logp):
    _seed(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s",
         "reserved_cny": 10 ** 400},
    ])
    _assert_controlled_corrupt(logp)


def test_settled_huge_int_10pow400_controlled_corrupt(logp):
    _seed(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 10 ** 400},
    ])
    _assert_controlled_corrupt(logp)


def test_duplicate_settled_huge_int_controlled_corrupt(logp):
    _seed(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 0.001},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 10 ** 400},
    ])
    _assert_controlled_corrupt(logp)


def _extreme_int_literal(getter=None) -> str:
    """Pick a JSON integer literal that must be rejected as a ledger amount.

    - Runtime enforces a positive int-str digit limit: emit limit+10 digits
      (parse-time numeric failure -> controlled corrupt).
    - No limit API or limit == 0 (limit disabled): emit a 5000-digit literal,
      which parses fine but overflows float conversion -> the amount validator
      must reject it (still a controlled corrupt).

    R1.7 Task A: `get_int_max_str_digits()` may RETURN 0 when the limit is
    disabled; `limit + 10` would then build a harmless 10-digit integer.
    """
    if getter is None:
        getter = getattr(sys, "get_int_max_str_digits", None)
    limit = getter() if getter is not None else 0
    if limit and limit > 0:
        return "9" * (limit + 10)
    return "9" * 5000


def test_digit_limit_literal_controlled_corrupt(logp):
    """A JSON integer literal beyond the runtime's int_str_digits limit must
    also end in a controlled corrupt state (parse-time ValueError), not an
    escaping exception. This runtime (3.10.1) has no such limit, in which case
    the literal parses and the overflow validator must still corrupt it."""
    literal = _extreme_int_literal()
    logp.write_text(
        '{"request_id": "a", "state": "RESERVED", "scope": "s", '
        f'"reserved_cny": {literal}}}\n', encoding="utf-8")
    _assert_controlled_corrupt(logp)


def test_digit_limit_zero_means_unlimited_falls_back_to_overflow():
    """R1.7 regression: when the digit-limit API reports 0 (limit DISABLED),
    the fixture must still be an extreme literal (5000 digits) — never a short
    limit+10 integer. Scoped monkeypatch; no global interpreter change."""
    getter = lambda: 0
    assert len(_extreme_int_literal(getter)) == 5000
    getter_pos = lambda: 4300
    assert len(_extreme_int_literal(getter_pos)) == 4310
    # and the current runtime's actual choice is one of the two extreme forms
    assert len(_extreme_int_literal()) >= 4310


def test_normal_finite_int_and_float_amounts_replay(logp):
    """Guard: ordinary finite int and float amounts stay valid accounting."""
    _seed(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s/A", "reserved_cny": 1},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 2},
        {"request_id": "b", "state": "RESERVED", "scope": "s/B", "reserved_cny": 0.01},
        {"request_id": "b", "state": "SENT"},
        {"request_id": "b", "state": "SETTLED", "cost_cny": 0.004},
    ])
    with _mk(logp, upstream_base_url="http://127.0.0.1:1",
             max_requests_per_task=10, global_cap_cny=5.0) as proxy:
        snap = proxy.snapshot()
        assert snap["ledger_corrupt"] is False
        assert snap["known_cost_cny"] == pytest.approx(2.004)
        assert snap["stopped"] is False


def test_validation_is_total_no_exception_leaks(logp):
    """Direct property: _valid_amount never raises, for any decoded value."""
    from causalevo.eval.budget_proxy import _valid_amount
    samples = [10 ** 400, -(10 ** 400), 0, 1, 2.5, -0.1, float("nan"),
               float("inf"), -float("inf"), True, False, None, "0.01",
               [1], {"a": 1}, 1e308, -1e308, 10 ** 4300]
    for v in samples:
        result = _valid_amount(v)  # must not raise
        assert isinstance(result, bool)
    assert _valid_amount(1) and _valid_amount(2.5) and _valid_amount(0)
    assert not _valid_amount(10 ** 400)


def test_proxy_construction_never_raises_on_extreme_ledger(logp):
    """End-to-end contract: __init__ of a proxy over an extreme ledger returns
    a serving (but stopped) object instead of raising."""
    _seed(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s",
         "reserved_cny": 10 ** 400},
        {"request_id": "b", "state": "RESERVED", "scope": "s2", "reserved_cny": 0.01},
        {"request_id": "b", "state": "SENT"},
        {"request_id": "b", "state": "SETTLED", "cost_cny": 0.004},
    ])
    with _mk(logp, upstream_base_url="http://127.0.0.1:1",
             max_requests_per_task=10, global_cap_cny=5.0) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True
