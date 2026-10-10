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
check('neg', sum_digits(-123), 6)
check('zero', sum_digits(0), 0)
check('neg_zero', sum_digits(-5), 5)
check('big', sum_digits(9999), 36)
check('ten', sum_digits(10), 1)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
