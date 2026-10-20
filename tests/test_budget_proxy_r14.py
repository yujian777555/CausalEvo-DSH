"""P4-R1.4: output-token-limit strictness, scoped UNKNOWN reconcile, and
duplicate-event conflict regression tests. Appended to the budget proxy suite
(these FAIL on the R1.3 implementation by design — defect reproduction)."""

import json

import pytest

from causalevo.eval.budget_proxy import BudgetProxy, ProxyConfig
from causalevo.eval.fake_provider import FakeProvider

from test_budget_proxy import _mk, _post  # reuse the suite's helpers


@pytest.fixture
def logp(tmp_path):
    return tmp_path / "ledger.jsonl"


# ---------------------------------------------------------------------------
# P0-A: output token limit must be strict fail-closed
# ---------------------------------------------------------------------------

def _post_body(url, **body):
    base = {"model": "deepseek-flash", "messages": [{"role": "user", "content": "hi"}]}
    base.update(body)
    return _post(url, body=base)


@pytest.mark.parametrize("bad", [
    {},                                            # missing both fields
    {"max_tokens": None},                          # null
    {"max_tokens": "256"},                         # string
    {"max_tokens": 256.0},                         # float
    {"max_tokens": True},                          # bool
    {"max_tokens": -5},                            # negative
    {"max_tokens": 0},                             # zero
    {"max_tokens": 10**9},                         # way over cap
    {"max_completion_tokens": None},               # alias null
    {"max_completion_tokens": "256"},              # alias string
    {"max_completion_tokens": 3.5},                # alias float
    {"max_tokens": 100, "max_completion_tokens": 200},  # conflicting pair
    {"max_tokens": "100", "max_completion_tokens": "100"},  # pair, wrong type
])
def test_output_limit_illegal_values_rejected_pre_send(logp, bad):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0, worst_case_output_tokens=2048) as proxy:
            code, _ = _post_body(proxy.base_url, **bad)
            assert code in (400, 403), f"{bad} must be rejected, got {code}"
            assert up.call_count == 0, f"illegal output limit reached upstream: {bad}"
            assert proxy.snapshot()["per_scope"] == {}, "no budget consumed"


def test_output_limit_legal_boundaries_pass(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0, worst_case_output_tokens=2048) as proxy:
            assert _post_body(proxy.base_url, max_tokens=1)[0] == 200
            assert _post_body(proxy.base_url, max_tokens=2048)[0] == 200, \
                "exactly at cap must pass"
            assert _post_body(proxy.base_url, max_completion_tokens=2048)[0] == 200
            # identical alias pair: proven-consistent, allowed by the frozen rule
            assert _post_body(proxy.base_url, max_tokens=64,
                              max_completion_tokens=64)[0] == 200
            assert up.call_count == 4


def test_output_limit_rejection_audited(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy:
            _post_body(proxy.base_url)  # missing output limit
            _post_body(proxy.base_url, max_tokens="x")
    audits = [json.loads(l) for l in logp.read_text().splitlines() if l.strip()]
    reasons = [e.get("reason") for e in audits if e.get("state") == "REJECTED"]
    assert sum(1 for r in reasons if r and r.startswith("output_limit")) == 2
    blob = json.dumps(audits)
    assert "content" not in blob or "hi" not in blob, "no prompt text in audit"


# ---------------------------------------------------------------------------
# P0-B: scope-aware UNKNOWN reconciliation
# ---------------------------------------------------------------------------

def _force_unknown(proxy, scope):
    """Drive one request into UNKNOWN via the public path (upstream 500)."""
    proxy.set_current_scope(scope)
    code, _ = _post_body(proxy.base_url, max_tokens=8)
    assert code == 500


def _seed_two_scope_unknowns(logp):
    """A crash with TWO in-flight requests in DIFFERENT scopes (the realistic
    way multiple scopes can hold simultaneous UNKNOWNs: the first unknown
    stops the gate, so only a crash leaves several unsettled)."""
    entries = [
        {"request_id": "rid-A", "state": "RESERVED", "scope": "run/t/1/A",
         "reserved_cny": 0.03},
        {"request_id": "rid-A", "state": "SENT"},
        {"request_id": "rid-B", "state": "RESERVED", "scope": "run/t/1/B",
         "reserved_cny": 0.03},
        {"request_id": "rid-B", "state": "SENT"},
    ]
    logp.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def test_runtime_unknown_then_scoped_reconcile(logp):
    with FakeProvider(lambda m, i: [("error", 500, {"error": "x"})]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy:
            _force_unknown(proxy, "run/t/1/A")
            assert proxy.snapshot()["stopped"] is True
            cleared = proxy.reconcile(scope="run/t/1/A")
            assert len(cleared) == 1
            assert proxy.snapshot()["stopped"] is False


def test_scoped_reconcile_only_clears_its_own_scope(logp):
    """A and B both UNKNOWN (crash-recovered): reconcile(A) must keep the gate
    stopped by B; only reconcile(B) releases it. History never zeroes."""
    _seed_two_scope_unknowns(logp)
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy:
            snap = proxy.snapshot()
            assert snap["stopped"] is True
            assert len(snap["unresolved_unknown"]) == 2
            assert snap["per_scope"] == {"run/t/1/A": 1, "run/t/1/B": 1}
            cleared = proxy.reconcile(scope="run/t/1/A")
            assert cleared == ["rid-A"]
            snap = proxy.snapshot()
            assert snap["stopped"] is True, "B's UNKNOWN must keep the gate stopped"
            assert snap["unresolved_unknown"] == ["rid-B"]
            proxy.set_current_scope("run/t/1/A")
            assert _post_body(proxy.base_url, max_tokens=8)[0] == 429
            assert up.call_count == 0
            cleared_b = proxy.reconcile(scope="run/t/1/B")
            assert cleared_b == ["rid-B"]
            assert proxy.snapshot()["stopped"] is False
            proxy.set_current_scope("run/t/1/A")
            assert _post_body(proxy.base_url, max_tokens=8)[0] == 200
            assert up.call_count == 1
            snap = proxy.snapshot()
            assert snap["per_scope"] == {"run/t/1/A": 2, "run/t/1/B": 1}, \
                "reconcile never zeroes per-scope counts"
    with FakeProvider(lambda m, i: [("text", "ok")]) as up2:
        with _mk(logp, upstream_base_url=up2.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy2:
            assert proxy2.snapshot()["stopped"] is False, \
                "both scopes reconciled: replay resumes"


def test_scoped_reconcile_survives_restart_partial(logp):
    """Reconcile A, THEN restart: B must still block (replay consistency)."""
    _seed_two_scope_unknowns(logp)
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy:
            proxy.reconcile(scope="run/t/1/A")
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy2:
            snap = proxy2.snapshot()
            assert snap["stopped"] is True
            assert snap["unresolved_unknown"] == ["rid-B"]
            proxy2.set_current_scope("run/t/1/A")
            assert _post_body(proxy2.base_url, max_tokens=8)[0] == 429


def test_reconcile_rejects_empty_scope_and_unknown_ids(logp):
    with FakeProvider(lambda m, i: [("error", 500, {"error": "x"})]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy:
            _force_unknown(proxy, "run/t/1/A")
            with pytest.raises(Exception):
                proxy.reconcile(scope="")
            with pytest.raises(Exception):
                proxy.reconcile_requests(["no-such-request-id"], reason="x")
            with pytest.raises(Exception):
                proxy.reconcile_requests([], reason="x")
            assert proxy.snapshot()["stopped"] is True, "still blocked"


def test_cross_scope_reconcile_requires_explicit_ids_and_reason(logp):
    _seed_two_scope_unknowns(logp)
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=50.0) as proxy:
            rids = sorted(proxy.snapshot()["unresolved_unknown"])
            assert rids == ["rid-A", "rid-B"]
            # explicit cross-scope clearance by request id list
            cleared = proxy.reconcile_requests(rids, reason="ops review ticket-7")
            assert cleared == rids
            assert proxy.snapshot()["stopped"] is False
    controls = [json.loads(l) for l in logp.read_text().splitlines()
                if l.strip() and '"control"' in l]
    rec = [c for c in controls if c.get("control") == "manual_reconcile"]
    assert any(c.get("reason") == "ops review ticket-7"
               and isinstance(c.get("cleared"), list) for c in rec)


def test_replay_rejects_reconcile_with_foreign_scope_rids(logp):
    """A reconcile event whose cleared ids do NOT belong to its scope is
    overreach: replay must mark the ledger corrupt (fail-closed)."""
    entries = [
        {"request_id": "a", "state": "RESERVED", "scope": "s/A", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "UNKNOWN"},
        {"request_id": "b", "state": "RESERVED", "scope": "s/B", "reserved_cny": 0.01},
        {"request_id": "b", "state": "SENT"},
        {"request_id": "b", "state": "UNKNOWN"},
        # overreach: scope s/A clearing rid b (which belongs to s/B)
        {"control": "manual_reconcile", "scope": "s/A", "cleared": ["a", "b"]},
    ]
    logp.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True


def test_replay_rejects_reconcile_of_unknown_ids(logp):
    entries = [
        {"request_id": "a", "state": "RESERVED", "scope": "s/A", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "UNKNOWN"},
        {"control": "manual_reconcile", "scope": "s/A", "cleared": ["ghost-rid"]},
    ]
    logp.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True


# ---------------------------------------------------------------------------
# P1-E: duplicate same-state events must be semantically identical
# ---------------------------------------------------------------------------

def _ledger_with_duplicate_reserved(logp, scope2, reserved2):
    entries = [
        {"request_id": "a", "state": "RESERVED", "scope": "s/A", "reserved_cny": 0.01},
        {"request_id": "a", "state": "RESERVED", "scope": scope2, "reserved_cny": reserved2},
    ]
    logp.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def test_duplicate_reserved_identical_is_idempotent(logp):
    _ledger_with_duplicate_reserved(logp, "s/A", 0.01)
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        snap = proxy.snapshot()
        assert snap["ledger_corrupt"] is False
        assert snap["per_scope"] == {"s/A": 1}


def test_duplicate_reserved_conflicting_scope_corrupts(logp):
    _ledger_with_duplicate_reserved(logp, "s/B", 0.01)
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True


def test_duplicate_reserved_conflicting_amount_corrupts(logp):
    _ledger_with_duplicate_reserved(logp, "s/A", 0.02)
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True
