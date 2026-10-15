"""Per-request budget proxy tests (P4-R1.1-S3). All offline on 127.0.0.1."""

import json
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from causalevo.eval.budget_proxy import BudgetProxy, ProxyConfig
from causalevo.eval.fake_provider import FakeProvider


def _post(url, task="t1", body=None, env=None):
    req = urllib.request.Request(
        url + "/chat/completions",
        data=json.dumps(body or {"messages": [{"role": "user", "content": "hi"}],
                                 "model": "deepseek-flash"}).encode(),
        headers={"Content-Type": "application/json", "X-Task-Id": task})
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, resp.read()
    except urllib.error.HTTPError as e:
        return e.code, e.read()


@pytest.fixture
def log_path(tmp_path):
    return tmp_path / "ledger.jsonl"


def _proxy(live_log, **kw):
    cfg = ProxyConfig(upstream_base_url=kw.pop("upstream"), **kw)
    return BudgetProxy(cfg, live_log).start()


def test_happy_path_three_requests_settled(log_path):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _proxy(log_path, upstream=up.base_url, max_requests_per_task=10,
                    global_cap_cny=5.0) as proxy:
            for _ in range(3):
                status, _ = _post(proxy.base_url)
                assert status == 200
            snap = proxy.snapshot()
            assert snap["requests"] == 3
            assert snap["known_cost_cny"] > 0
            assert snap["stopped"] is False


def test_per_task_cap_rejects_before_forwarding(log_path):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _proxy(log_path, upstream=up.base_url, max_requests_per_task=3,
                    global_cap_cny=5.0) as proxy:
            for _ in range(3):
                assert _post(proxy.base_url)[0] == 200
            status, body = _post(proxy.base_url)
            assert status == 429
            assert up.call_count == 3, "4th request must be rejected BEFORE sending"


def test_global_budget_rejects_before_send(log_path):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _proxy(log_path, upstream=up.base_url, max_requests_per_task=99,
                    global_cap_cny=0.0001) as proxy:
            status, body = _post(proxy.base_url)
            assert status == 429
            assert up.call_count == 0, "over-budget request must never reach upstream"


def test_duplicate_inflight_body_rejected(log_path):
    barrier = threading.Barrier(2)
    # slow upstream guarantees the two identical requests overlap in-flight
    with FakeProvider(lambda m, i: [("sleep", 0.6), ("text", "ok")]) as up:
        with _proxy(log_path, upstream=up.base_url, max_requests_per_task=10,
                    global_cap_cny=5.0) as proxy:
            results = []
            def go():
                barrier.wait()
                results.append(_post(proxy.base_url, body={"messages": [{"role": "user", "content": "same"}]})[0])
            t1, t2 = threading.Thread(target=go), threading.Thread(target=go)
            t1.start(); t2.start(); t1.join(); t2.join()
            assert sorted(results) == [200, 429]


def test_upstream_500_stops_all_further_requests(log_path):
    with FakeProvider(lambda m, i: [("error", 500, {"error": "boom"})]) as up:
        with _proxy(log_path, upstream=up.base_url, max_requests_per_task=10,
                    global_cap_cny=5.0) as proxy:
            status, _ = _post(proxy.base_url)
            assert status == 500
            assert proxy.snapshot()["stopped"] is True
            status2, _ = _post(proxy.base_url)
            assert status2 == 429, "after unknown-cost stop, no more sends"
            assert up.call_count == 1


def test_missing_usage_fails_closed(log_path):
    # upstream 200 but no usage anywhere
    def no_usage(messages, i):
        return [("text", "ok")]
    with FakeProvider(no_usage) as up:
        # FakeProvider always attaches usage; use a raw broken upstream instead
        pass
    class NoUsage(BaseHTTPRequestHandler):
        def do_POST(self):
            body = b'data: {"id":"x","choices":[{"delta":{"content":"hi"},"finish_reason":"stop"}],"object":"chat.completion.chunk"}\n\ndata: [DONE]\n\n'
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        def log_message(self, *a):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), NoUsage)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with _proxy(log_path, upstream=f"http://127.0.0.1:{server.server_address[1]}",
                max_requests_per_task=10, global_cap_cny=5.0) as proxy:
        status, _ = _post(proxy.base_url)
        assert status == 200
        assert proxy.snapshot()["stopped"] is True
        assert proxy.snapshot()["unknown_spend"] == 1
        assert _post(proxy.base_url)[0] == 429
    server.shutdown()


def test_stream_reset_fails_closed(log_path):
    class Reset(BaseHTTPRequestHandler):
        def do_POST(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(b'data: {"id":"x"}\n\n')  # partial, then drop
            self.connection.close()
        def log_message(self, *a):
            pass
    server = ThreadingHTTPServer(("127.0.0.1", 0), Reset)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with _proxy(log_path, upstream=f"http://127.0.0.1:{server.server_address[1]}",
                max_requests_per_task=10, global_cap_cny=5.0) as proxy:
        _post(proxy.base_url)
        assert proxy.snapshot()["stopped"] is True


def test_unauthorized_never_forwards(log_path):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _proxy(log_path, upstream=up.base_url, max_requests_per_task=10,
                    global_cap_cny=5.0, authorized=False) as proxy:
            assert _post(proxy.base_url)[0] == 429
            assert up.call_count == 0


def test_ledger_persisted_after_every_event(log_path):
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _proxy(log_path, upstream=up.base_url, max_requests_per_task=10,
                    global_cap_cny=5.0) as proxy:
            _post(proxy.base_url)
            _post(proxy.base_url)
            content = log_path.read_text(encoding="utf-8")
            assert content.count("\n") >= 2  # one line per settled request


def test_no_env_proxy_honored_for_upstream(log_path, monkeypatch):
    """DIRECT proof: a bogus HTTP_PROXY in env must not break or reroute."""
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:1")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:1")
    with FakeProvider(lambda m, i: [("text", "ok")]) as up:
        with _proxy(log_path, upstream=up.base_url, max_requests_per_task=10,
                    global_cap_cny=5.0) as proxy:
            status, _ = _post(proxy.base_url)
            assert status == 200, "bogus env proxy must not affect upstream path"
