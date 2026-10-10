"""Scratch: single live smoke call. Verifies wire model, usage shape, no tools.

Cost: one short call (~1k prompt tokens + <=64 output), well under 0.01 CNY.
Prints a redacted structural digest of events; never prints the API key.
"""
import json
import pathlib

from deepseek_harness import DeepSeekHarness, DeepSeekHarnessConfig

root = pathlib.Path("results/phase0/tmp").resolve()
dsh_home = root / "dsh_home"
ws = root / "ws"
dsh_home.mkdir(parents=True, exist_ok=True)
ws.mkdir(parents=True, exist_ok=True)

cfg = DeepSeekHarnessConfig(
    provider="deepseek-official",
    model="deepseek-flash",
    reasoning_effort="low",
    max_tokens=64,
    cwd=str(ws),
    dsh_home=str(dsh_home),
    patches=(str(pathlib.Path("configs/dsh_bench_patch.yml").resolve()),),
    initialize_timeout_seconds=60.0,
    request_timeout_seconds=180.0,
    env={"DSH_PERMISSION_MODE": "read-only"},
)

with DeepSeekHarness(cfg) as h:
    result = h.run(
        "Reply with exactly one minified JSON object {\"task\":\"T000\",\"status\":\"ok\"} and no other text.",
        session_id="ce-dsh-p0-smoke",
    )

print("finish_reason:", result.finish_reason)
print("final_response:", repr(result.final_response[:200]))
print("event_count:", len(result.events))
types = {}
for e in result.events:
    types[e.get("type")] = types.get(e.get("type"), 0) + 1
print("event_types:", json.dumps(types, indent=2))

# Show full structure of usage-bearing / model-bearing events (keys only + usage values)
for e in result.events:
    s = json.dumps(e)
    if "sage" in s or "odel" in s or "tool" in s:
        print("EVENT:", json.dumps(e)[:2000])
