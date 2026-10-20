"""Standalone tape server: serves a precomputed action tape over the
OpenAI-compatible SSE wire format. Stdlib-only by design so it can run inside
a bare python:3.11-slim container with no project dependencies.

Usage: python tape_server.py /tape/tape.json  (binds 0.0.0.0:8080)

Tape format: {"0": [["tool_call", "read", {"file_path": "solution.py"}], ...], ...}
Out-of-range call indices receive a plain text completion so the agent loop
terminates. "sleep" actions hang the response (timeout testing). "no_usage"
suppresses the usage chunk (unknown-cost fail-closed testing). Every POST is
counted in /tape/requests.jsonl (upstream-side receive counter).
"""

from __future__ import annotations

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def _chunk(delta: dict, finish: str | None = None, usage: dict | None = None) -> str:
    obj = {
        "id": "tape", "object": "chat.completion.chunk", "created": 0,
        "model": "deepseek-flash",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    if usage:
        obj["usage"] = usage
    return "data: " + json.dumps(obj) + "\n\n"


def render(actions: list, call_index: int) -> bytes:
    tool_calls = [a for a in actions if a[0] == "tool_call"]
    texts = [a for a in actions if a[0] == "text"]
    suppress_usage = any(a[0] == "no_usage" for a in actions)
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
        parts.append(_chunk({"role": "assistant",
                             "content": "".join(t[1] for t in texts) or "done"}))
        finish = "stop"
    usage = {
        "prompt_tokens": 100 + call_index * 50,
        "completion_tokens": 5 + 5 * len(actions),
        "total_tokens": 105 + call_index * 50,
        "prompt_cache_hit_tokens": 64,
        "prompt_cache_miss_tokens": 36 + call_index * 50,
    }
    parts.append(_chunk({}, finish=finish, usage=None if suppress_usage else usage))
    parts.append("data: [DONE]\n\n")
    return "".join(parts).encode()


def main() -> int:
    tape_path = Path(sys.argv[1])
    tape = json.loads(tape_path.read_text(encoding="utf-8"))
    observations_path = tape_path.parent / "observations.jsonl"
    requests_path = tape_path.parent / "requests.jsonl"
    counter = {"n": 0}

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            # upstream-side request counter: every POST that REACHED this
            # provider, appended before any processing (host-side assertions)
            try:
                with open(requests_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"i": counter["n"],
                                         "bytes": length}) + "\n")
            except Exception:
                pass
            try:
                parsed = json.loads(body or b"{}")
                with open(observations_path, "a", encoding="utf-8") as fh:
                    for m in parsed.get("messages", []):
                        if m.get("role") == "tool":
                            fh.write(json.dumps({"call": counter["n"],
                                                 "content": m.get("content", "")}) + "\n")
            except Exception:
                pass
            idx = counter["n"]
            counter["n"] += 1
            actions = tape.get(str(idx), [["text", "done"]])
            error = next((a for a in actions if a[0] == "error"), None)
            if error is not None:
                body = json.dumps(error[2]).encode()
                self._send(error[1], body, "application/json")
                return
            for a in actions:
                if a[0] == "sleep":
                    time.sleep(float(a[1]))
            actions = [a for a in actions if a[0] != "sleep"]
            self._send(200, render(actions, idx), "text/event-stream")

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    ThreadingHTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
