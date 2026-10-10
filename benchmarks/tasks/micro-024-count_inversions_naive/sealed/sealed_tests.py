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
check('sorted', count_inversions([1, 2, 3]), 0)
check('reverse', count_inversions([3, 2, 1]), 3)
check('equal', count_inversions([2, 2]), 0)
check('mixed', count_inversions([1, 3, 2]), 1)
check('empty', count_inversions([]), 0)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
