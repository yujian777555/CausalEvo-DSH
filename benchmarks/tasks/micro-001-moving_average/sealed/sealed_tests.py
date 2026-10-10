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
check('single', moving_average([1.0, 2.0], 1), [1.0, 2.0])
check('full', moving_average([2.0, 4.0], 2), [3.0])
check('three', moving_average([0.0, 3.0, 3.0, 6.0], 3), [2.0, 4.0])
check('length', len(moving_average([1.0]*10, 4)), 7)
check('exact', moving_average([5.0], 1), [5.0])
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
