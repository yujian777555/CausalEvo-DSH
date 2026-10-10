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
check('below', clamp_value(-3, 0, 10), 0)
check('above', clamp_value(99, 0, 10), 10)
check('at_lo', clamp_value(0, 0, 10), 0)
check('at_hi', clamp_value(10, 0, 10), 10)
check('float', clamp_value(2.5, 0.0, 2.0), 2.0)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
