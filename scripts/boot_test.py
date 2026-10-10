"""Scratch: offline boot test of the no-tools patched runtime (no API call)."""
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
    env={"DSH_PERMISSION_MODE": "read-only"},
)
h = DeepSeekHarness(cfg)
h.start()
print("HANDSHAKE OK: runtime started, initialize() succeeded with no-tools patch")
h.close()
print("CLOSED OK")
