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
check('all_neg', max_subarray([-5, -2, -9]), -2)
check('single', max_subarray([-7]), -7)
check('all_pos', max_subarray([1, 2, 3]), 6)
check('mixed', max_subarray([2, -1, 2]), 3)
check('zero', max_subarray([0, -1, 0]), 0)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
