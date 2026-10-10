import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from solution import *  # noqa
_failures = []
def check(name, actual, expected):
    if actual != expected:
        _failures.append((name, actual, expected))
        print(f'FAIL {name}: got {actual!r} want {expected!r}')
    else:
        print(f'PASS {name}')
check('runs', dedup_adjacent([1, 1, 2, 2, 1]), [1, 2, 1])
check('all_same', dedup_adjacent([3, 3, 3]), [3])
check('none_adj', dedup_adjacent([1, 2, 1]), [1, 2, 1])
check('empty', dedup_adjacent([]), [])
check('mixed', dedup_adjacent([0, 0, 1, 0, 0]), [0, 1, 0])
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
