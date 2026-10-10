"""Scenario assignment, session IDs, prompt determinism, length invariants."""

from causalevo.scenarios import (
    build_call_plan,
    check_length_invariants,
    full_prompt,
    make_prefix,
    prefix_variant,
    session_id,
    task_suffix,
)


def test_four_groups_assignment_and_interleave():
    plan = build_call_plan(25, "runxyz", interleave=True)
    assert len(plan) == 100
    assert [c.group for c in plan[:4]] == ["A", "B", "C", "D"]  # round-robin
    for group in "ABCD":
        assert sum(1 for c in plan if c.group == group) == 25
        assert sorted(c.index for c in plan if c.group == group) == list(range(25))


def test_session_id_rules():
    a_ids = {session_id("A", i, "runxyz") for i in range(25)}
    assert len(a_ids) == 1, "group A must share one session"
    for group in "BCD":
        ids = {session_id(group, i, "runxyz") for i in range(25)}
        assert len(ids) == 25, f"group {group} must use a fresh session per call"
    assert session_id("B", 0, "runxyz") == session_id("B", 0, "runxyz")
    assert session_id("B", 0, "runxyz") != session_id("B", 0, "other")


def test_prompt_determinism():
    for group in "ABCD":
        for i in (0, 7, 24):
            assert full_prompt(group, i) == full_prompt(group, i)


def test_b_and_c_share_identical_prefix():
    b = full_prompt("B", 0)
    c = full_prompt("C", 3)
    assert b.startswith(make_prefix())
    assert c.startswith(make_prefix())
    assert b != c and full_prompt("B", 0) == full_prompt("B", 9)


def test_d_prefix_varies_early_but_length_fixed():
    base = make_prefix()
    d5 = full_prompt("D", 5)
    assert not d5.startswith(base) or prefix_variant(5) != base
    assert len(prefix_variant(5)) == len(base)
    # difference appears early (inside the Bench-ID line, not at the end)
    diff_at = next(i for i, (x, y) in enumerate(zip(prefix_variant(5), base)) if x != y)
    assert diff_at < len(base) // 2


def test_suffix_fixed_length_and_unique():
    suffixes = {task_suffix(i) for i in range(25)}
    assert len(suffixes) == 25
    assert len({len(s) for s in suffixes}) == 1


def test_length_invariants_hold_for_25():
    check_length_invariants(25)  # raises on drift
