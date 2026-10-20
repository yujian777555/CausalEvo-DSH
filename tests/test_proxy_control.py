"""P4-R1.3 S3: generation-based proxy control channel unit tests (offline,
no docker): repeated scopes, A->B->A switches, delayed/stale ACKs, generation
mismatch and shared-mount failure all behave deterministically."""

import json
import threading
import time
from pathlib import Path

import pytest

from causalevo.eval.proxy_control import (ACK_NAME, CONTROL_NAME,
                                          ControlChannelError, apply_control,
                                          await_ack, publish_control)


class _FakeProxy:
    def __init__(self):
        self.scopes = []

    def set_current_scope(self, scope):
        self.scopes.append(scope)


def _proxy_side_once(proxy, ledger_dir, last_gen):
    data = json.loads((ledger_dir / CONTROL_NAME).read_text(encoding="utf-8"))
    return apply_control(proxy, data, last_gen, ledger_dir / ACK_NAME)


def test_publish_clears_stale_ack_first(tmp_path):
    (tmp_path / ACK_NAME).write_text('{"generation": 99, "scope": "old"}',
                                     encoding="utf-8")
    publish_control(tmp_path, 1, "run/t/1/B0")
    assert not (tmp_path / ACK_NAME).exists(), "stale ack removed before publish"
    data = json.loads((tmp_path / CONTROL_NAME).read_text(encoding="utf-8"))
    assert data == {"generation": 1, "scope": "run/t/1/B0"}


def test_roundtrip_and_repeated_identical_scope(tmp_path):
    """R1.2 bug: two consecutive IDENTICAL task scopes deadlocked the old
    data-equality ack loop. Generations make every publish distinct."""
    proxy = _FakeProxy()
    last = -1
    for gen in (1, 2, 3):
        publish_control(tmp_path, gen, "run/t/1/B0")  # same scope every time
        last = _proxy_side_once(proxy, tmp_path, last)
        ack = await_ack(tmp_path, gen, timeout_s=2)
        assert ack["generation"] == gen and ack["scope"] == "run/t/1/B0"
    assert proxy.scopes == ["run/t/1/B0"] * 3, "every generation applied once"


def test_fast_ab_switch_and_stale_generation_ignored(tmp_path):
    proxy = _FakeProxy()
    publish_control(tmp_path, 1, "A")
    last = _proxy_side_once(proxy, tmp_path, -1)
    publish_control(tmp_path, 2, "B")
    last = _proxy_side_once(proxy, tmp_path, last)
    publish_control(tmp_path, 3, "A")
    last = _proxy_side_once(proxy, tmp_path, last)
    assert proxy.scopes == ["A", "B", "A"]
    # a stale (replayed) older generation must be ignored without ack
    stale = apply_control(proxy, {"generation": 2, "scope": "B"}, last,
                          tmp_path / ACK_NAME)
    assert stale == last == 3
    assert proxy.scopes == ["A", "B", "A"]
    # malformed messages are ignored too
    assert apply_control(proxy, {"scope": "no-gen"}, last,
                         tmp_path / ACK_NAME) == 3
    assert apply_control(proxy, {"generation": "x", "scope": "y"}, last,
                         tmp_path / ACK_NAME) == 3
    assert apply_control(proxy, {"generation": 4, "scope": ""}, last,
                         tmp_path / ACK_NAME) == 3
    assert proxy.scopes == ["A", "B", "A"]


def test_await_ack_timeout_raises(tmp_path):
    publish_control(tmp_path, 7, "run/t/1/B0")  # nobody acks
    with pytest.raises(ControlChannelError):
        await_ack(tmp_path, 7, timeout_s=0.5)


def test_await_ack_newer_generation_detects_concurrent_publisher(tmp_path):
    publish_control(tmp_path, 3, "x")
    (tmp_path / ACK_NAME).write_text('{"generation": 9, "scope": "y"}',
                                     encoding="utf-8")
    with pytest.raises(ControlChannelError):
        await_ack(tmp_path, 3, timeout_s=2)


def test_publish_requires_shared_mount(tmp_path):
    with pytest.raises(ControlChannelError):
        publish_control(tmp_path / "missing", 1, "x")


def test_delayed_ack_still_accepted(tmp_path):
    proxy = _FakeProxy()

    def delayed_proxy():
        time.sleep(0.6)
        data = json.loads((tmp_path / CONTROL_NAME).read_text(encoding="utf-8"))
        apply_control(proxy, data, -1, tmp_path / ACK_NAME)

    publish_control(tmp_path, 1, "run/t/1/B0")
    t = threading.Thread(target=delayed_proxy)
    t.start()
    ack = await_ack(tmp_path, 1, timeout_s=3)
    t.join()
    assert ack["generation"] == 1
    assert proxy.scopes == ["run/t/1/B0"]


def test_concurrent_publishes_are_serialized_by_caller_lock(tmp_path):
    """The runner serializes scope sets with a lock; simulate two publishers
    behind the same lock and verify generations stay strictly increasing."""
    proxy = _FakeProxy()
    lock = threading.Lock()
    counter = {"gen": 0}
    last = -1
    for _ in range(5):
        with lock:
            counter["gen"] += 1
            gen = counter["gen"]
            publish_control(tmp_path, gen, f"scope-{gen}")
        last = _proxy_side_once(proxy, tmp_path, last)
        assert await_ack(tmp_path, gen, timeout_s=2)["generation"] == gen
    assert proxy.scopes == [f"scope-{i}" for i in range(1, 6)]
