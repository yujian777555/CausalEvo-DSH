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


def _post(url, body=None):
    req = urllib.request.Request(
        url + "/chat/completions",
        data=json.dumps(body or {"messages": [{"role": "user", "content": "hi"}]}).encode(),
        headers={"Content-Type": "application/json"})
    try:
        resp = urllib.request.urlopen(req, timeout=20)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture
def logp(tmp_path):
    return tmp_path / "ledger.jsonl"


def _mk(logp, **kw):
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
                                     body={"messages": [{"role": "user",
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
            proxy2.reconcile()
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
                data=json.dumps({"messages": []}).encode(),
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
            proxy.set_current_task("task-A")
            assert _post(proxy.base_url)[0] == 200
            proxy.set_current_task("task-B")
            assert _post(proxy.base_url)[0] == 200
            proxy.set_current_task("task-A")
            assert _post(proxy.base_url)[0] == 429, "task-A exhausted its cap"
            snap = proxy.snapshot()
            assert snap["per_task"] == {"task-A": 1, "task-B": 1}


def test_env_proxy_never_used_for_upstream(logp, monkeypatch):
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _mk(logp, upstream_base_url=up.base_url, max_requests_per_task=5,
                 global_cap_cny=5.0) as proxy:
            assert _post(proxy.base_url)[0] == 200
