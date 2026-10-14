"""Create the Phase 1.6 sample private holdout OUTSIDE the repo.

Content never enters git; only benchmarks/holdout_manifest.json (hashes) is
committed. Re-run is idempotent (same content -> same hashes).
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from causalevo.eval.holdout import store_root, write_holdout_task, write_manifest  # noqa: E402

TASKS = [
    dict(
        task_id="holdout-001-clamp01", split="holdout", function="clamp01",
        instructions="solution.py provides clamp01(x): clamp x into [0.0, 1.0]. It is buggy. Fix it.",
        buggy="def clamp01(x):\n    return min(max(x, 1.0), 0.0)\n",
        fixed="def clamp01(x):\n    return min(max(x, 0.0), 1.0)\n",
        visible="from solution import clamp01\nassert clamp01(0.5) == 0.5\nprint('ok')\n",
        sealed="from solution import clamp01\nassert clamp01(-1.0) == 0.0\nassert clamp01(2.0) == 1.0\nassert clamp01(0.0) == 0.0\nassert clamp01(1.0) == 1.0\nprint('ok')\n",
    ),
    dict(
        task_id="holdout-002-count_consonants", split="holdout", function="count_consonants",
        instructions="solution.py provides count_consonants(s): count ASCII consonants (case-insensitive). It is buggy. Fix it.",
        buggy="def count_consonants(s):\n    return sum(1 for c in s.lower() if c.isalpha())\n",
        fixed="def count_consonants(s):\n    return sum(1 for c in s.lower() if c.isalpha() and c not in 'aeiou')\n",
        visible="from solution import count_consonants\nassert count_consonants('bcd') == 3\nprint('ok')\n",
        sealed="from solution import count_consonants\nassert count_consonants('aeiou') == 0\nassert count_consonants('Hello World') == 7\nassert count_consonants('') == 0\nprint('ok')\n",
    ),
    dict(
        task_id="holdout-003-lcm", split="holdout", function="lcm",
        instructions="solution.py provides lcm(a, b): least common multiple of positive integers. It is buggy. Fix it.",
        buggy="def lcm(a, b):\n    return (a * b) // __import__('math').gcd(a, b) if a != b else a + b\n",
        fixed="def lcm(a, b):\n    import math\n    return (a * b) // math.gcd(a, b)\n",
        visible="from solution import lcm\nassert lcm(4, 6) == 12\nprint('ok')\n",
        sealed="from solution import lcm\nassert lcm(5, 5) == 5\nassert lcm(3, 7) == 21\nassert lcm(1, 1) == 1\nprint('ok')\n",
    ),
]


def main() -> int:
    root = store_root()
    root.mkdir(parents=True, exist_ok=True)
    for spec in TASKS:
        write_holdout_task(root, **spec)
    m = write_manifest(root)
    print(f"holdout store: {root} ({m['count']} tasks; content outside git)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
