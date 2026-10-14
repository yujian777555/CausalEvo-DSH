"""Tape transform tests (P2.3-S3): pure functions, original never mutated."""

import pytest

from causalevo.counterfactual.replay import apply_tape_transform

TAPE = {
    "0": [["tool_call", "definitely_not_a_tool", {"x": 1}]],
    "1": [["tool_call", "write", {"file_path": "solution.py", "content": "fixed"}]],
    "2": [["text", "done"]],
}

SPAM_TAPE = {
    "0": [["tool_call", "glob", {"pattern": "**/*"}]],
    "1": [["tool_call", "glob", {"pattern": "**/*"}]],
    "2": [["tool_call", "glob", {"pattern": "**/*"}]],
    "3": [["tool_call", "glob", {"pattern": "**/*"}]],
}


def _flat(tape):
    return [a for k in sorted(tape, key=int) for a in tape[k]]


def test_identity_unchanged():
    new, changes = apply_tape_transform(TAPE, "identity", entry_file="s.py", fixed_content="x")
    assert new == TAPE and changes == []


def test_original_tape_never_mutated():
    import copy
    snapshot = copy.deepcopy(TAPE)
    apply_tape_transform(TAPE, "replace_unknown_tool_with_read",
                         entry_file="solution.py", fixed_content="x")
    assert TAPE == snapshot


def test_replace_unknown_tool():
    new, changes = apply_tape_transform(TAPE, "replace_unknown_tool_with_read",
                                        entry_file="solution.py", fixed_content="x")
    assert changes
    assert new["0"][0][1] == "read"
    assert new["0"][0][2] == {"file_path": "solution.py"}
    assert new["1"] == TAPE["1"]  # known tools untouched


def test_prepend_read_step():
    new, changes = apply_tape_transform(TAPE, "prepend_read_step",
                                        entry_file="solution.py", fixed_content="x")
    assert new["0"][0][1] == "read"
    assert new["1"] == TAPE["0"]  # shifted
    assert len(new) == len(TAPE) + 1


def test_append_readback_and_fix():
    new, changes = apply_tape_transform(TAPE, "append_readback_and_fix",
                                        entry_file="solution.py", fixed_content="CORRECT")
    assert changes
    flat = _flat(new)
    write_idx = next(i for i, a in enumerate(flat) if a[0] == "tool_call" and a[1] == "write")
    assert flat[write_idx + 1][1] == "read"
    assert flat[write_idx + 2][1] == "write"
    assert flat[write_idx + 2][2]["content"] == "CORRECT"


def test_append_readback_without_write_is_noop():
    tape = {"0": [["text", "done"]]}
    new, changes = apply_tape_transform(tape, "append_readback_and_fix",
                                        entry_file="s.py", fixed_content="x")
    assert new == tape and changes == []


def test_break_repeat_with_read():
    new, changes = apply_tape_transform(SPAM_TAPE, "break_repeat_with_read",
                                        entry_file="solution.py", fixed_content="x")
    assert changes
    flat = _flat(new)
    # loop cut: read inserted, then terminal text
    assert any(a[0] == "tool_call" and a[1] == "read" for a in flat)
    assert flat[-1][0] == "text"
    assert sum(1 for a in flat if a[0] == "tool_call" and a[1] == "glob") <= 2


def test_break_repeat_no_spam_is_noop():
    new, changes = apply_tape_transform(TAPE, "break_repeat_with_read",
                                        entry_file="s.py", fixed_content="x")
    assert new == TAPE and changes == []


def test_inject_fix_alias():
    new, _ = apply_tape_transform(TAPE, "inject_fix_after_write",
                                  entry_file="solution.py", fixed_content="F")
    flat = _flat(new)
    assert any(a[0] == "tool_call" and a[1] == "write" and a[2]["content"] == "F"
               for a in flat)


def test_unknown_transform_raises():
    with pytest.raises(ValueError):
        apply_tape_transform(TAPE, "nope", entry_file="s.py", fixed_content="x")


def test_tape_keys_renumber_contiguously():
    new, _ = apply_tape_transform(TAPE, "prepend_read_step",
                                  entry_file="s.py", fixed_content="x")
    assert sorted(new, key=int) == [str(i) for i in range(len(new))]
