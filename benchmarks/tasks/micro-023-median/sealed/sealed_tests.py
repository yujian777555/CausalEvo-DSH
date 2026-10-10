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
check('even', median([1, 2, 3, 4]), 2.5)
check('two', median([1, 10]), 5.5)
check('one', median([7]), 7.0)
check('unsorted', median([9, 1, 5]), 5.0)
check('even_neg', median([-4, -2]), -3.0)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
