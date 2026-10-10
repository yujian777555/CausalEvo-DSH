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
check('absent', binary_search([1, 3, 5], 4), -1)
check('first', binary_search([1, 3, 5], 1), 0)
check('last', binary_search([1, 3, 5], 5), 2)
check('empty', binary_search([], 1), -1)
check('absent_high', binary_search([1, 2], 99), -1)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
