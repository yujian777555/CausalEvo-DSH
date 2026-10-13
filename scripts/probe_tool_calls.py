"""Scratch: dump the tool schemas the task profile exposes, then exercise a
tool-call round trip (write_file via fake provider) and log the flow."""
import json
import pathlib
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

LOG = []
TOOL_DUMP = pathlib.Path("results/phase1/r2-scratch/tools.json")
RESPONSE_MODE = {"n": 0}  # 1st request -> tool_call, 2nd -> final text


def chunk(delta, finish=None, usage=False):
    obj = {"id": "fake", "object": "chat.completion.chunk", "created": 0,
           "model": "deepseek-flash",
           "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    if usage:
        obj["usage"] = {"prompt_tokens": 100, "completion_tokens": 5, "total_tokens": 105,
                        "prompt_cache_hit_tokens": 64, "prompt_cache_miss_tokens": 36}
    return "data: " + json.dumps(obj) + "\n\n"


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        parsed = json.loads(self.rfile.read(length) or b"{}")
        LOG.append(parsed)
        RESPONSE_MODE["n"] += 1
        if RESPONSE_MODE["n"] == 1:
            # tool call: write_file via tool-fs
            payload = (
                chunk({"role": "assistant", "tool_calls": [{
                    "index": 0, "id": "call_1", "type": "function",
                    "function": {"name": "write",
                                 "arguments": json.dumps({"file_path": "solution.py",
                                                          "content": "def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi)\n"})}}]})
                + chunk({}, finish="tool_calls", usage=True)
                + "data: [DONE]\n\n"
            ).encode()
        else:
            payload = (
                chunk({"role": "assistant", "content": "DONE_FIXApplied"})
                + chunk({}, finish="stop", usage=True)
                + "data: [DONE]\n\n"
            ).encode()
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

root = pathlib.Path("results/phase1/r2-scratch").resolve()
(d := root / "dsh_home3").mkdir(parents=True, exist_ok=True)
(w := root / "ws3").mkdir(parents=True, exist_ok=True)
(w / "solution.py").write_text("# buggy\n", encoding="utf-8")

cfg = DeepSeekHarnessConfig(
    provider="deepseek-official", model="deepseek-flash", reasoning_effort="low",
    max_tokens=256, cwd=str(w), dsh_home=str(d),
    patches=(str(pathlib.Path("configs/dsh_task_patch.yml").resolve()),),
    initialize_timeout_seconds=60.0, request_timeout_seconds=120.0,
    base_url=f"http://127.0.0.1:{port}", api_key="sk-fake-offline-no-cost",
)
with DeepSeekHarness(cfg) as h:
    result = h.run("Fix the bug in solution.py", session_id="fake-toolcall-1")

print("finish_reason:", result.finish_reason)
print("final_response:", repr(result.final_response[:200]))
print("workspace solution.py now:", (w / 'solution.py').read_text()[:80].replace(chr(10), ' | '))
print("=== request 2 messages tail (tool result shape) ===")
if len(LOG) > 1:
    print(json.dumps(LOG[1]["messages"][-2:], ensure_ascii=False)[:1500])
print("=== event types ===")
types = {}
for e in result.events:
    types[e.get("type")] = types.get(e.get("type"), 0) + 1
print(json.dumps(types, indent=1))
TOOL_DUMP.write_text(json.dumps(LOG[0].get("tools", []), indent=2)[:8000], encoding="utf-8")
print("tool names:", [t.get("function", {}).get("name") for t in LOG[0].get("tools", [])])
