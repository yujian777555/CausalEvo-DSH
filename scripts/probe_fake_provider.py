"""Scratch: discover the wire format the deepseek-official adapter speaks.

Runs a local HTTP server that LOGS requests and returns a minimal canned
completion, then points the SDK at it via DEEPSEEK_BASE_URL. Offline; the
"API key" is a fake string.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = []


class Handler(BaseHTTPRequestHandler):
    def _send_json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        LOG.append(("GET", self.path, None))
        if self.path.endswith("/models"):
            self._send_json({"object": "list", "data": [
                {"id": "deepseek-flash", "object": "model"}]})
        else:
            self._send_json({"ok": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        try:
            parsed = json.loads(body)
        except Exception:
            parsed = None
        LOG.append(("POST", self.path, parsed))
        if self.path.endswith("/chat/completions"):
            stream = bool(parsed and parsed.get("stream"))
            if stream:
                payload = (
                    'data: {"id":"fake-1","object":"chat.completion.chunk","created":0,'
                    '"model":"deepseek-flash","choices":[{"index":0,"delta":{"role":"assistant","content":"FAKE_REPLY"},"finish_reason":null}]}\n\n'
                    'data: {"id":"fake-1","object":"chat.completion.chunk","created":0,'
                    '"model":"deepseek-flash","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],'
                    '"usage":{"prompt_tokens":100,"completion_tokens":5,"total_tokens":105,'
                    '"prompt_cache_hit_tokens":64,"prompt_cache_miss_tokens":36}}\n\n'
                    "data: [DONE]\n\n"
                ).encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            else:
                self._send_json({
                    "id": "fake-1", "object": "chat.completion", "created": 0,
                    "model": "deepseek-flash",
                    "choices": [{"index": 0, "finish_reason": "stop",
                                 "message": {"role": "assistant", "content": "FAKE_REPLY"}}],
                    "usage": {"prompt_tokens": 100, "completion_tokens": 5,
                              "total_tokens": 105, "prompt_cache_hit_tokens": 64,
                              "prompt_cache_miss_tokens": 36},
                })
        else:
            self._send_json({"ok": True})

    def log_message(self, *a):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()
print("fake provider on", port)

from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig
import pathlib

root = pathlib.Path("results/phase1/r2-scratch").resolve()
(d := root / "dsh_home").mkdir(parents=True, exist_ok=True)
(w := root / "ws").mkdir(parents=True, exist_ok=True)

cfg = DeepSeekHarnessConfig(
    provider="deepseek-official",
    model="deepseek-flash",
    reasoning_effort="low",
    max_tokens=64,
    cwd=str(w),
    dsh_home=str(d),
    patches=(str(pathlib.Path("configs/dsh_task_patch.yml").resolve()),),
    initialize_timeout_seconds=60.0,
    request_timeout_seconds=60.0,
    base_url=f"http://127.0.0.1:{port}",
    api_key="sk-fake-offline-no-cost",
)
with DeepSeekHarness(cfg) as h:
    result = h.run("Say something.", session_id="fake-probe-1")

print("finish_reason:", result.finish_reason)
print("final_response:", repr(result.final_response[:200]))
print("=== logged requests ===")
for method, path, parsed in LOG:
    print(method, path)
    if parsed:
        keys = {k: (type(v).__name__ if not isinstance(v, (str, int, bool)) else v) for k, v in parsed.items()}
        print("  fields:", json.dumps(keys, ensure_ascii=False)[:600])
print("=== usage-bearing events ===")
for e in result.events:
    s = json.dumps(e)
    if '"usage"' in s:
        print(json.dumps(e)[:800])
