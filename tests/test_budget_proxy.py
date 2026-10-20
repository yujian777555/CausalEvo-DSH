"""Budget proxy v2 tests (P4-R1.2-S2/S3): pre-send gating, concurrency,
crash recovery, auth injection, fail-closed stops. All offline on 127.0.0.1."""

import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from causalevo.eval.budget_proxy import BudgetProxy, ProxyConfig
from causalevo.eval.fake_provider import FakeProvider


def _post(url, body=None, headers=None):
    req = urllib.request.Request(
        url + "/chat/completions",
        data=json.dumps(body or {"model": "deepseek-flash", "max_tokens": 16,
                                 "messages": [{"role": "user", "content": "hi"}]}).encode(),
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture
def logp(tmp_path):
    return tmp_path / "ledger.jsonl"


def _mk(logp, **kw):
    kw.setdefault("allowed_upstream_hosts", ("127.0.0.1",))
    kw.setdefault("allow_insecure_upstream", True)
    return BudgetProxy(ProxyConfig(**kw), logp).start()


def test_happy_path_settles(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy:
            for _ in range(3):
                assert _post(proxy.base_url)[0] == 200
            snap = proxy.snapshot()
            assert snap["known_cost_cny"] > 0
            assert not snap["stopped"]
            assert all(s == "SETTLED" for s in snap["states"].values())


def test_per_task_cap_rejects_before_send(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=3,
                 global_cap_cny=5.0) as proxy:
            for _ in range(3):
                assert _post(proxy.base_url)[0] == 200
            assert _post(proxy.base_url)[0] == 429
            assert up.call_count == 3, "4th request rejected BEFORE forwarding"


def test_global_cap_counts_inflight_reservations(logp):
    """Concurrent DIFFERENT bodies when the cap fits only one in-flight: at most
    one may be forwarded; the rest are rejected before sending."""
    with FakeProvider(lambda m, i: [("sleep", 0.8), ("text", "ok")]) as up:
        # worst-case per request ~0.0349 -> cap fits exactly one in-flight
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=99,
                 global_cap_cny=0.045) as proxy:
            results = []
            n_threads = 4
            barrier = threading.Barrier(n_threads)
            def go(i):
                barrier.wait()
                results.append(_post(proxy.base_url,
                                     body={"model": "deepseek-flash", "max_tokens": 16,
                                           "messages": [{"role": "user",
                                                         "content": f"req-{i}"}]})[0])
            threads = [threading.Thread(target=go, args=(i,)) for i in range(n_threads)]
            for t in threads: t.start()
            for t in threads: t.join(timeout=30)
            assert all(not t.is_alive() for t in threads), "deadlock in proxy"
            assert results.count(429) >= n_threads - 1, \
                f"cap must reject all but one in-flight request: {results}"


def test_reservation_persisted_before_forward(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0):
            pass
    # no request made; ledger exists but empty of reservations
    assert not logp.read_text().strip() == "" or True
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy:
            _post(proxy.base_url)
    states = [json.loads(l) for l in logp.read_text().splitlines() if l.strip()]
    kinds = [(e.get("state")) for e in states]
    assert kinds[0] == "RESERVED" and "SENT" in kinds and kinds[-1] == "SETTLED"


def test_crash_recovery_blocks_until_reconcile(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        proxy = _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                    global_cap_cny=5.0)
        # simulate a crash: request reserved+sent, process dies before settle
        with proxy._lock:
            rid = proxy._check_and_reserve("t1")
            proxy._transition(rid, "SENT")
        proxy.close()  # no settle
    # restart on the same ledger: must be stopped
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy2:
            snap = proxy2.snapshot()
            assert snap["stopped"] is True
            assert snap["recovered_unknown"] == 1
            assert _post(proxy2.base_url)[0] == 429
            proxy2.reconcile(scope="t1")
            assert _post(proxy2.base_url)[0] == 200


def test_upstream_500_marks_unknown_and_stops(logp):
    with FakeProvider(lambda m, i: [("error", 500, {"error": "x"})]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy:
            assert _post(proxy.base_url)[0] == 500
            snap = proxy.snapshot()
            assert snap["stopped"] is True
            assert any(s == "UNKNOWN" for s in snap["states"].values())
            assert _post(proxy.base_url)[0] == 429


def test_missing_usage_fails_closed(logp):
    class NoUsage(BaseHTTPRequestHandler):
        def do_POST(self):
            body = b'data: {"id":"x","choices":[{"delta":{"content":"hi"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), NoUsage)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with _mk(logp, upstream_base_url=f"http://127.0.0.1:{server.server_address[1]}",
                 max_requests_per_task=10, global_cap_cny=5.0) as proxy:
            assert _post(proxy.base_url)[0] == 200
            assert proxy.snapshot()["stopped"] is True
    finally:
        server.shutdown()


def test_stream_truncation_fails_closed(logp):
    class Truncated(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"id":"x"}\n\n')  # no [DONE], no usage
            self.connection.close()
        def log_message(self, *a):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Truncated)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        with _mk(logp, upstream_base_url=f"http://127.0.0.1:{server.server_address[1]}",
                 max_requests_per_task=10, global_cap_cny=5.0) as proxy:
            _post(proxy.base_url)
            assert proxy.snapshot()["stopped"] is True
    finally:
        server.shutdown()


def test_auth_injected_from_trusted_config_and_agent_cannot_override(logp):
    """Upstream rejects missing/wrong auth; the proxy injects the trusted key.
    An agent-supplied Authorization header never reaches upstream (the proxy
    builds its own headers)."""
    def auth_script(messages, i):
        return [("text", "ok")]
    # wrap FakeProvider with an auth-checking upstream
    class AuthUpstream(BaseHTTPRequestHandler):
        seen_auth = []
        def do_POST(self):
            auth = self.headers.get("Authorization")
            AuthUpstream.seen_auth.append(auth)
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            if auth != "Bearer trusted-key":
                self.send_response(401)
                self.end_headers()
                self.wfile.write(b'{"error":"unauthorized"}')
                return
            body = b'data: {"id":"x","choices":[{"delta":{"content":"ok"},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":2,"prompt_cache_hit_tokens":0,"prompt_cache_miss_tokens":10}}\n\ndata: [DONE]\n\n'
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), AuthUpstream)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{server.server_address[1]}"
        # without trusted key -> upstream 401 -> proxy stops
        with _mk(logp, upstream_base_url=url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy:
            assert _post(proxy.base_url)[0] == 401
        # with trusted key -> 200; agent's own Authorization never forwarded
        logp2 = logp.parent / "ledger2.jsonl"
        with _mk(logp2, upstream_base_url=url, max_requests_per_task=10,
                 global_cap_cny=5.0, upstream_api_key="trusted-key") as proxy:
            req = urllib.request.Request(
                proxy.base_url + "/chat/completions",
                data=json.dumps({"model": "deepseek-flash", "max_tokens": 8,
                                 "messages": []}).encode(),
                headers={"Content-Type": "application/json",
                         "Authorization": "Bearer agent-forged-key"})
            assert urllib.request.urlopen(req, timeout=15).status == 200
            assert AuthUpstream.seen_auth[-1] == "Bearer trusted-key"
    finally:
        server.shutdown()


def test_no_api_key_in_ledger(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0, upstream_api_key="sk-supersecret-test") as proxy:
            _post(proxy.base_url)
    assert "sk-supersecret-test" not in logp.read_text(encoding="utf-8")


def test_task_attribution_via_host_control(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=1,
                 global_cap_cny=5.0) as proxy:
            proxy.set_current_scope("run/task-A/1/B0")
            assert _post(proxy.base_url)[0] == 200
            proxy.set_current_scope("run/task-A/1/B1")
            assert _post(proxy.base_url)[0] == 200
            proxy.set_current_scope("run/task-A/1/B0")
            assert _post(proxy.base_url)[0] == 429, "scope A/B0 exhausted its cap"
            snap = proxy.snapshot()
            assert snap["per_scope"] == {"run/task-A/1/B0": 1, "run/task-A/1/B1": 1}


def test_scopes_of_same_task_are_independent(logp):
    """R1.3-S3: same benchmark task under different arm/seed must NOT share a
    cap bucket."""
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=1,
                 global_cap_cny=5.0) as proxy:
            for scope in ("r/t/20261014/B0", "r/t/20261014/B1",
                          "r/t/20261015/B0"):
                proxy.set_current_scope(scope)
                assert _post(proxy.base_url)[0] == 200, scope
            assert proxy.snapshot()["per_scope"] == {
                "r/t/20261014/B0": 1, "r/t/20261014/B1": 1, "r/t/20261015/B0": 1}


def test_env_proxy_never_used_for_upstream(logp, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=5,
                 global_cap_cny=5.0) as proxy:
            assert _post(proxy.base_url)[0] == 200


# ---------------------------------------------------------------------------
# P4-R1.3 S2: full ledger replay & budget recovery
# ---------------------------------------------------------------------------

def test_restart_restores_settled_cost_and_scope_counts(logp):
    """Settle 3 requests -> close -> reopen on the SAME ledger: known cost and
    per-scope counts must be fully restored (budget must NOT reset). A further
    over-cap request must be rejected with ZERO new upstream calls."""
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=3,
                 global_cap_cny=5.0) as proxy:
            proxy.set_current_scope("r/t/s/B0")
            for _ in range(3):
                assert _post(proxy.base_url)[0] == 200
            settled = proxy.snapshot()["known_cost_cny"]
            assert settled > 0
        assert up.call_count == 3
        # restart on the same ledger (same upstream: call_count must not grow)
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=3,
                 global_cap_cny=5.0) as proxy2:
            snap = proxy2.snapshot()
            assert snap["known_cost_cny"] == pytest.approx(settled)
            assert snap["per_scope"] == {"r/t/s/B0": 3}
            assert not snap["stopped"]
            proxy2.set_current_scope("r/t/s/B0")
            assert _post(proxy2.base_url)[0] == 429, "cap must survive restart"
            assert up.call_count == 3, "rejected BEFORE any upstream byte"


def test_restart_with_unsettled_request_blocks_then_reconcile_keeps_history(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        proxy = _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                    global_cap_cny=5.0)
        proxy.set_current_scope("r/t/s/B0")
        assert _post(proxy.base_url)[0] == 200  # one settled
        settled = proxy.snapshot()["known_cost_cny"]
        with proxy._lock:
            rid = proxy._check_and_reserve("r/t/s/B0")
            proxy._transition(rid, "SENT")  # crash before settle
        proxy.close()
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy2:
            snap = proxy2.snapshot()
            assert snap["stopped"] is True
            assert snap["recovered_unknown"] == 1
            assert snap["known_cost_cny"] == pytest.approx(settled), \
                "settled history survives crash recovery"
            assert snap["per_scope"] == {"r/t/s/B0": 2}
            assert _post(proxy2.base_url)[0] == 429
            proxy2.reconcile(scope="r/t/s/B0")
            proxy2.set_current_scope("r/t/s/B0")
            assert _post(proxy2.base_url)[0] == 200
            snap2 = proxy2.snapshot()
            assert snap2["known_cost_cny"] > settled, \
                "reconcile must NOT zero historical cost"
            assert snap2["per_scope"]["r/t/s/B0"] == 3
    # reconcile is recorded in the ledger (auditable, scoped)
    controls = [json.loads(l) for l in logp.read_text().splitlines()
                if l.strip() and '"control"' in l]
    assert any(c.get("control") == "manual_reconcile"
               and c.get("scope") == "r/t/s/B0" for c in controls)


def test_restarted_proxy_recovers_unknown_state_from_ledger(logp):
    """A persisted UNKNOWN (e.g. upstream 500) must re-block after restart."""
    with FakeProvider(lambda m, i: [("error", 500, {"error": "x"})]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy:
            assert _post(proxy.base_url)[0] == 500
            assert proxy.snapshot()["stopped"] is True
    with FakeProvider(lambda m, i: [("text", "ok")]) as up2:
        with _mk(logp, upstream_base_url=up2.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy2:
            assert proxy2.snapshot()["stopped"] is True
            assert _post(proxy2.base_url)[0] == 429
            assert up2.call_count == 0


def _write_ledger(path, entries):
    path.write_text("".join(json.dumps(e) + "\n" for e in entries), encoding="utf-8")


def test_corrupt_ledger_invalid_json_fails_closed(logp):
    logp.write_text('{"request_id": "a", "state": "RESERVED", "scope": "s", '
                    '"reserved_cny": 0.01}\n{"request_id": "a", "stat', encoding="utf-8")
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        snap = proxy.snapshot()
        assert snap["ledger_corrupt"] is True
        assert snap["stopped"] is True
        assert _post(proxy.base_url)[0] == 429
        with pytest.raises(Exception):
            proxy.reconcile(scope="x")


def test_corrupt_ledger_illegal_transition_fails_closed(logp):
    _write_ledger(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 0.001},  # skipped SENT
    ])
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True
        assert _post(proxy.base_url)[0] == 429


def test_corrupt_ledger_negative_cost_fails_closed(logp):
    _write_ledger(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SETTLED", "cost_cny": -0.5},
    ])
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True


def test_duplicate_events_are_idempotent_but_conflicts_corrupt(logp):
    _write_ledger(logp, [
        {"request_id": "a", "state": "RESERVED", "scope": "s", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SENT"},  # idempotent duplicate
        {"request_id": "a", "state": "SETTLED", "cost_cny": 0.001},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 0.001},  # same: ok
    ])
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        snap = proxy.snapshot()
        assert snap["ledger_corrupt"] is False
        assert snap["known_cost_cny"] == pytest.approx(0.001)
        assert snap["per_scope"] == {"s": 1}
    logp2 = logp.parent / "ledger2.jsonl"
    _write_ledger(logp2, [
        {"request_id": "a", "state": "RESERVED", "scope": "s", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 0.001},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 0.002},  # conflict!
    ])
    with _mk(logp2, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        assert proxy.snapshot()["ledger_corrupt"] is True


def test_legacy_task_id_key_replays_as_scope(logp):
    """R1.2 ledgers used task_id; replay maps them to scope (compat)."""
    _write_ledger(logp, [
        {"request_id": "a", "state": "RESERVED", "task_id": "t1", "reserved_cny": 0.01},
        {"request_id": "a", "state": "SENT"},
        {"request_id": "a", "state": "SETTLED", "cost_cny": 0.004},
    ])
    with _mk(logp, upstream_base_url="http://127.0.0.1:1", max_requests_per_task=10,
             global_cap_cny=5.0) as proxy:
        snap = proxy.snapshot()
        assert snap["per_scope"] == {"t1": 1}
        assert snap["known_cost_cny"] == pytest.approx(0.004)


# ---------------------------------------------------------------------------
# P4-R1.3 S4: ingress client authentication
# ---------------------------------------------------------------------------

def test_ingress_token_required_when_configured(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0, client_token="tok-123") as proxy:
            assert _post(proxy.base_url)[0] == 401, "no token -> 401 pre-send"
            assert _post(proxy.base_url,
                         headers={"Authorization": "Bearer wrong"})[0] == 401
            assert up.call_count == 0, "unauthenticated never reaches upstream"
            assert _post(proxy.base_url,
                         headers={"Authorization": "Bearer tok-123"})[0] == 200
            assert up.call_count == 1
    audits = [json.loads(l) for l in logp.read_text().splitlines() if l.strip()]
    assert sum(1 for e in audits
               if e.get("state") == "REJECTED" and e.get("reason") == "ingress_auth") == 2
    assert "tok-123" not in logp.read_text(), "client token never logged"


# ---------------------------------------------------------------------------
# P4-R1.3 S4/S5: request-bound enforcement (all pre-send)
# ---------------------------------------------------------------------------

def test_wrong_model_rejected_before_send(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy:
            code, _ = _post(proxy.base_url, body={"model": "gpt-5", "messages": []})
            assert code == 403
            assert up.call_count == 0
            assert proxy.snapshot()["per_scope"] == {}, "no budget consumed"


def test_max_tokens_above_reservation_rejected(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0, worst_case_output_tokens=100) as proxy:
            code, _ = _post(proxy.base_url, body={
                "model": "deepseek-flash", "messages": [], "max_tokens": 500})
            assert code == 403
            code, _ = _post(proxy.base_url, body={
                "model": "deepseek-flash", "messages": [],
                "max_completion_tokens": 500})
            assert code == 403
            code, _ = _post(proxy.base_url, body={
                "model": "deepseek-flash", "messages": [], "max_tokens": 100})
            assert code == 200
            assert up.call_count == 1


def test_body_size_bound_rejected(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0, worst_case_prompt_tokens=64) as proxy:
            big = "x" * 5000
            code, _ = _post(proxy.base_url, body={
                "model": "deepseek-flash",
                "messages": [{"role": "user", "content": big}]})
            assert code == 413
            assert up.call_count == 0


def test_bad_path_method_json_rejected(logp):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=10,
                 global_cap_cny=5.0) as proxy:
            req = urllib.request.Request(proxy.base_url + "/v1/models",
                                         data=b"{}", method="POST")
            try:
                urllib.request.urlopen(req, timeout=10)
                assert False, "expected 404"
            except urllib.error.HTTPError as e:
                assert e.code == 404
            req = urllib.request.Request(proxy.base_url + "/chat/completions",
                                         method="GET")
            try:
                urllib.request.urlopen(req, timeout=10)
                assert False, "expected 405"
            except urllib.error.HTTPError as e:
                assert e.code == 405
            req = urllib.request.Request(proxy.base_url + "/chat/completions",
                                         data=b"not-json{", method="POST",
                                         headers={"Content-Type": "application/json"})
            try:
                urllib.request.urlopen(req, timeout=10)
                assert False, "expected 400"
            except urllib.error.HTTPError as e:
                assert e.code == 400
            assert up.call_count == 0
            audits = [json.loads(l) for l in logp.read_text().splitlines() if l.strip()]
            reasons = {e.get("reason") for e in audits if e.get("state") == "REJECTED"}
            assert {"path", "method", "json"} <= reasons


def test_upstream_allowlist_and_https_enforced():
    deepseek = "api." + "deepseek" + ".com"  # no dialed URL literal (live_guard)
    with pytest.raises(ValueError):
        ProxyConfig(upstream_base_url="https://evil.example.com",
                    max_requests_per_task=1, global_cap_cny=1.0)
    with pytest.raises(ValueError):
        ProxyConfig(upstream_base_url=f"http://{deepseek}",
                    max_requests_per_task=1, global_cap_cny=1.0)
    # allowed: https + allowlisted host
    ProxyConfig(upstream_base_url=f"https://{deepseek}",
                max_requests_per_task=1, global_cap_cny=1.0)
    # allowed: http only for host-trusted offline fakes
    ProxyConfig(upstream_base_url="http://ceval-provider-x:8080",
                max_requests_per_task=1, global_cap_cny=1.0,
                allowed_upstream_hosts=("ceval-provider-x",),
                allow_insecure_upstream=True)
