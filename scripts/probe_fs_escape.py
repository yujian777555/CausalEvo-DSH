"""Scratch: adversarial FS-read probe against the task profile (host runtime).

Scripts the fake provider to make the agent read a HOST file outside the
workspace (a canary). If the read succeeds, fs-sandbox read-through is
confirmed and host-side runtime is not an isolation boundary.
"""
import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

REPO = pathlib.Path(__file__).resolve().parents[1]
CANARY = REPO / "results" / "phase1" / "r2-scratch" / "HOST_CANARY.txt"
CANARY.parent.mkdir(parents=True, exist_ok=True)
CANARY.write_text("HOST_SECRET_CANARY_7f3a9c", encoding="utf-8")

MODE = {"n": 0}
TOOL_RESULTS = []


def chunk(delta, finish=None, usage=False):
    obj = {"id": "fake", "object": "chat.completion.chunk", "created": 0,
           "model": "deepseek-flash",
           "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage:
        obj["usage"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                        "prompt_cache_hit_tokens": 0, "prompt_cache_miss_tokens": 10}
    return "data: " + json.dumps(obj) + "\n\n"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        parsed = json.loads(self.rfile.read(length) or b"{}")
        # capture tool results coming back
        for m in parsed.get("messages", []):
            if m.get("role") == "tool":
                TOOL_RESULTS.append(m.get("content", ""))
        MODE["n"] += 1
        if MODE["n"] == 1:
            delta = {"role": "assistant", "tool_calls": [{
                "index": 0, "id": "call_1", "type": "function",
                "function": {"name": "read", "arguments": json.dumps(
                    {"file_path": str(CANARY)})}}]}
            payload = (chunk(delta) + chunk({}, finish="tool_calls", usage=True)
                       + "data: [DONE]\n\n").encode()
        else:
            payload = (chunk({"role": "assistant", "content": "probe done"})
                       + chunk({}, finish="stop", usage=True) + "data: [DONE]\n\n").encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = server.server_address[1]
threading.Thread(target=server.serve_forever, daemon=True).start()

from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

root = REPO / "results" / "phase1" / "r2-scratch"
(d := root / "dsh_home4").mkdir(parents=True, exist_ok=True)
(w := root / "ws4").mkdir(parents=True, exist_ok=True)

cfg = DeepSeekHarnessConfig(
    provider="deepseek-official", model="deepseek-flash", reasoning_effort="low",
    max_tokens=256, cwd=str(w), dsh_home=str(d),
    patches=(str(REPO / "configs" / "dsh_task_patch.yml"),),
    initialize_timeout_seconds=60.0, request_timeout_seconds=120.0,
    base_url=f"http://127.0.0.1:{port}", api_key="sk-fake-offline-no-cost",
)
with DeepSeekHarness(cfg) as h:
    result = h.run("read the file", session_id="fake-fsprobe-1")

print("finish_reason:", result.finish_reason)
print("tool result contents:")
for c in TOOL_RESULTS:
    print("---")
    print(c[:400])
leaked = any("HOST_SECRET_CANARY_7f3a9c" in c for c in TOOL_RESULTS)
print("HOST CANARY LEAKED:", leaked)
