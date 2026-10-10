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
check('two', second_largest([10, 20]), 10)
check('dups', second_largest([5, 5, 9, 9, 2]), 5)
check('neg', second_largest([-1, -5, -3]), -3)
check('sorted', second_largest([1, 2, 3, 4]), 3)
check('reverse', second_largest([4, 3, 2, 1]), 3)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
