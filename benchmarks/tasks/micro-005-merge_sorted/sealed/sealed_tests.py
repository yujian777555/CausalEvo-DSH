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
check('empty_left', merge_sorted([], [1]), [1])
check('empty_right', merge_sorted([1], []), [1])
check('interleave', merge_sorted([1, 5, 9], [2, 3, 10]), [1, 2, 3, 5, 9, 10])
check('dup', merge_sorted([1, 1], [1]), [1, 1, 1])
check('neg', merge_sorted([-5, 0], [-3]), [-5, -3, 0])
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
