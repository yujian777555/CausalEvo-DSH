"""F4: redaction precision + effective config fingerprint."""

from pathlib import Path

from causalevo.benchmark import (
    BenchConfig,
    config_hash,
    effective_config_fingerprint,
    load_config,
)
from causalevo.redaction import redact_obj

REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = REPO_ROOT / "configs" / "cache_benchmark.yaml"
PATCH_PATH = REPO_ROOT / "configs" / "dsh_bench_patch.yml"


def test_numeric_token_fields_are_preserved():
    payload = {"max_tokens": 64, "prompt_overhead_tokens": 2000, "output_tokens": 32}
    redacted = redact_obj(payload)
    assert redacted == payload, "numeric token config must survive redaction"


def test_secrets_are_redacted():
    payload = {
        "api_key": "sk-" + "x" * 32,
        "Authorization": "Bearer abc",
        "client_secret": "shh",
        "nested": {"token": "t" * 20},
    }
    redacted = redact_obj(payload)
    assert redacted["api_key"] == "[REDACTED]"
    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["client_secret"] == "[REDACTED]"
    assert redacted["nested"]["token"] == "[REDACTED]"


def test_cli_overrides_affect_effective_hash():
    """--calls/--max-cny style overrides mutate the effective config; the
    experiment fingerprint must track semantic fields while the legacy raw
    hash stays put."""
    base = load_config(CONFIG_PATH)
    overridden = load_config(CONFIG_PATH)
    object.__setattr__(overridden, "calls_per_group", 5)
    assert config_hash(base) == config_hash(overridden), "legacy raw hash ignores overrides (documented)"
    assert effective_config_fingerprint(base, patch_path=PATCH_PATH, sdk="0.1.5rc1") != \
        effective_config_fingerprint(overridden, patch_path=PATCH_PATH, sdk="0.1.5rc1")
    # budget cap is spend authorization, not experiment semantics
    capped = load_config(CONFIG_PATH)
    object.__setattr__(capped, "max_cny", 4.83)
    assert effective_config_fingerprint(base, patch_path=PATCH_PATH, sdk="0.1.5rc1") == \
        effective_config_fingerprint(capped, patch_path=PATCH_PATH, sdk="0.1.5rc1")


def test_patch_fingerprint_changes(tmp_path):
    config = load_config(CONFIG_PATH)
    fp1 = effective_config_fingerprint(config, patch_path=PATCH_PATH, sdk="0.1.5rc1")
    other_patch = tmp_path / "other.yml"
    other_patch.write_text("- id: tool-todo\n  disabled: true\n", encoding="utf-8")
    fp2 = effective_config_fingerprint(config, patch_path=other_patch, sdk="0.1.5rc1")
    fp3 = effective_config_fingerprint(config, patch_path=PATCH_PATH, sdk="0.1.5rc2")
    assert fp1 != fp2, "patch content must affect the fingerprint"
    assert fp1 != fp3, "SDK version must affect the fingerprint"
    assert fp1 == effective_config_fingerprint(config, patch_path=PATCH_PATH, sdk="0.1.5rc1")
