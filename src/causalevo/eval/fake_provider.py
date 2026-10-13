"""Scriptable fake LLM provider at the Harness protocol layer (offline).

Implements just enough of the OpenAI-compatible DeepSeek endpoint
(POST /chat/completions, SSE streaming) for the real deepseek-official
adapter to run the genuine Harness agent loop: request -> assistant message
(with tool_calls) -> tool execution in the workspace -> tool result ->
next request. Zero cost, no external network; binds 127.0.0.1 only.

The "model" is a script: a callable taking the request messages and the
call index and returning a list of actions: ("text", str) |
("tool_call", name, arguments_dict) | ("error", status_code, payload).
Usage numbers are synthetic but well-formed; they exercise accounting, they
are not measurements of a real provider.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

Action = tuple
Script = Callable[[list[dict[str, Any]], int], list[Action]]


def _chunk(delta: dict, finish: str | None = None, usage: dict | None = None) -> str:
    obj: dict[str, Any] = {
        "id": "fake", "object": "chat.completion.chunk", "created": 0,
        "model": "deepseek-flash",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if usage:
        obj["usage"] = usage
    return "data: " + json.dumps(obj) + "\n\n"


def render_response(actions: list[Action], call_index: int) -> bytes:
    """Render scripted actions as one SSE response."""
    tool_calls = [a for a in actions if a[0] == "tool_call"]
    texts = [a for a in actions if a[0] == "text"]
    parts: list[str] = []
    if tool_calls:
        calls = [
            {"index": i, "id": f"call_{call_index}_{i}", "type": "function",
             "function": {"name": name, "arguments": json.dumps(args)}}
            for i, (_t, name, args) in enumerate(tool_calls)
        ]
        parts.append(_chunk({"role": "assistant", "tool_calls": calls}))
        finish = "tool_calls"
    else:
        content = "".join(t[1] for t in texts)
        parts.append(_chunk({"role": "assistant", "content": content}))
        finish = "stop"
    usage = {
        "prompt_tokens": 100 + call_index * 50,
        "completion_tokens": 5 + 5 * len(actions),
        "total_tokens": 105 + call_index * 50,
        "prompt_cache_hit_tokens": 64,
        "prompt_cache_miss_tokens": 36 + call_index * 50,
    }
    parts.append(_chunk({}, finish=finish, usage=usage))
    parts.append("data: [DONE]\n\n")
    return "".join(parts).encode()


class FakeProvider:
    """Local HTTP server speaking the adapter's wire format.

    Actions the script may return: ("text", str) | ("tool_call", name, args) |
    ("error", status, payload) | ("sleep", seconds) — the last one hangs the
    response to exercise client-side timeout handling."""

    def __init__(self, script: Script) -> None:
        self.script = script
        self.requests: list[dict[str, Any]] = []  # full request bodies (offline, synthetic)
        self._lock = threading.Lock()
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                parsed = json.loads(self.rfile.read(length) or b"{}")
                with provider._lock:
                    call_index = len(provider.requests)
                    provider.requests.append(parsed)
                try:
                    actions = provider.script(parsed.get("messages", []), call_index)
                except Exception as exc:  # script bug -> visible 500
                    self._send(500, json.dumps({"error": str(exc)}).encode(),
                               "application/json")
                    return
                error = next((a for a in actions if a[0] == "error"), None)
                if error is not None:
                    self._send(error[1], json.dumps(error[2]).encode(), "application/json")
                    return
                sleep = next((a for a in actions if a[0] == "sleep"), None)
                if sleep is not None:
                    time.sleep(float(sleep[1]))  # provider hang simulation
                    # then fall through and answer normally
                payload = render_response([a for a in actions if a[0] != "sleep"], call_index)
                self._send(200, payload, "text/event-stream")

            def _send(self, status: int, body: bytes, content_type: str) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    @property
    def call_count(self) -> int:
        return len(self.requests)

    def tool_results(self) -> list[str]:
        out: list[str] = []
        for req in self.requests:
            for m in req.get("messages", []):
                if m.get("role") == "tool":
                    out.append(m.get("content", ""))
        return out

    def start(self) -> "FakeProvider":
        self._thread.start()
        return self

    def close(self) -> None:
        self._server.shutdown()
        self._server.server_close()

    def __enter__(self) -> "FakeProvider":
        return self.start()

    def __exit__(self, *exc) -> None:
        self.close()
