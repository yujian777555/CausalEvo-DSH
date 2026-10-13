"""FakeProvider wire-level tests: SSE rendering, logging, error/sleep actions."""

import json
import time
import urllib.error
import urllib.request

from causalevo.eval.fake_provider import FakeProvider


def _post(base_url: str, payload: dict) -> tuple[int, bytes]:
    req = urllib.request.Request(
        base_url + "/chat/completions",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, resp.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


def _chunks(body: bytes) -> list[dict]:
    out = []
    for block in body.decode().split("\n\n"):
        for line in block.splitlines():
            if line.startswith("data: ") and line != "data: [DONE]":
                out.append(json.loads(line[len("data: "):]))
    return out


def _payload(text: str = "hi") -> dict:
    return {"model": "deepseek-flash", "stream": True,
            "messages": [{"role": "user", "content": text}]}


def test_text_response_streams_role_content_stop_and_usage():
    with FakeProvider(lambda messages, call_index: [("text", "hello world")]) as provider:
        status, body = _post(provider.base_url, _payload())
    assert status == 200
    chunks = _chunks(body)
    assert chunks[0]["choices"][0]["delta"] == {
        "role": "assistant", "content": "hello world"}
    assert chunks[0]["choices"][0]["finish_reason"] is None
    final = chunks[-1]
    assert final["choices"][0]["finish_reason"] == "stop"
    assert final["usage"]["total_tokens"] > 0
    assert body.rstrip().endswith(b"data: [DONE]")


def test_tool_call_response_finish_reason_and_well_formed_calls():
    def script(messages, call_index):
        return [("tool_call", "read_file", {"path": "src/app.py"}),
                ("tool_call", "write_file", {"path": "out.txt", "content": "x"})]

    with FakeProvider(script) as provider:
        status, body = _post(provider.base_url, _payload())
    assert status == 200
    chunks = _chunks(body)
    calls = chunks[0]["choices"][0]["delta"]["tool_calls"]
    assert len(calls) == 2
    assert calls[0]["id"] == "call_0_0"
    assert calls[0]["type"] == "function"
    assert calls[0]["function"]["name"] == "read_file"
    assert json.loads(calls[0]["function"]["arguments"]) == {"path": "src/app.py"}
    assert calls[1]["id"] == "call_0_1"
    assert json.loads(calls[1]["function"]["arguments"]) == {
        "path": "out.txt", "content": "x"}
    assert chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"


def test_usage_carries_cache_hit_and_miss_tokens():
    with FakeProvider(lambda messages, call_index: [("text", "ok")]) as provider:
        status, body = _post(provider.base_url, _payload())
    assert status == 200
    usage = _chunks(body)[-1]["usage"]
    assert usage["prompt_cache_hit_tokens"] == 64
    assert usage["prompt_cache_miss_tokens"] == 36
    assert usage["prompt_tokens"] == 100
    assert usage["completion_tokens"] == 10
    assert usage["total_tokens"] == 105


def test_requests_logged_with_call_count_and_messages():
    with FakeProvider(lambda messages, call_index: [("text", "ok")]) as provider:
        assert provider.call_count == 0
        _post(provider.base_url, _payload("first"))
        _post(provider.base_url, _payload("second"))
        assert provider.call_count == 2
        assert provider.requests[0]["messages"] == [
            {"role": "user", "content": "first"}]
        assert provider.requests[1]["messages"] == [
            {"role": "user", "content": "second"}]


def test_tool_results_extracts_tool_message_contents():
    def script(messages, call_index):
        if call_index == 0:
            return [("tool_call", "read_file", {"path": "a.py"})]
        return [("text", "done")]

    with FakeProvider(script) as provider:
        _post(provider.base_url, _payload())
        followup = _payload()
        followup["messages"] += [
            {"role": "assistant", "content": None,
             "tool_calls": [{"id": "call_0_0", "type": "function",
                             "function": {"name": "read_file",
                                          "arguments": "{\"path\": \"a.py\"}"}}]},
            {"role": "tool", "tool_call_id": "call_0_0",
             "content": "FILE CONTENTS HERE"},
        ]
        _post(provider.base_url, followup)
        assert provider.tool_results() == ["FILE CONTENTS HERE"]


def test_error_action_returns_http_error_with_payload():
    def script(messages, call_index):
        return [("error", 500, {"error": {"message": "boom", "code": "x"}})]

    with FakeProvider(script) as provider:
        status, body = _post(provider.base_url, _payload())
    assert status == 500
    assert json.loads(body)["error"]["message"] == "boom"


def test_sleep_action_delays_but_completes():
    def script(messages, call_index):
        return [("sleep", 0.2), ("text", "slow answer")]

    with FakeProvider(script) as provider:
        start = time.perf_counter()
        status, body = _post(provider.base_url, _payload())
        elapsed = time.perf_counter() - start
    assert status == 200
    assert elapsed >= 0.15
    chunks = _chunks(body)
    assert chunks[0]["choices"][0]["delta"]["content"] == "slow answer"
    assert chunks[-1]["choices"][0]["finish_reason"] == "stop"


def test_sequential_calls_see_incrementing_call_index():
    seen: list[int] = []

    def script(messages, call_index):
        seen.append(call_index)
        return [("text", f"reply {call_index}")]

    with FakeProvider(script) as provider:
        misses = []
        for _ in range(3):
            status, body = _post(provider.base_url, _payload())
            assert status == 200
            misses.append(_chunks(body)[-1]["usage"]["prompt_cache_miss_tokens"])
    assert seen == [0, 1, 2]
    assert misses == [36, 86, 136]
