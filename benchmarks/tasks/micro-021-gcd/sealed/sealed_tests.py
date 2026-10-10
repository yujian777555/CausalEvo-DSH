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
check('coprime', gcd(7, 3), 1)
check('equal', gcd(5, 5), 5)
check('one', gcd(1, 9), 1)
check('big', gcd(1071, 462), 21)
check('reversed', gcd(8, 12), 4)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
