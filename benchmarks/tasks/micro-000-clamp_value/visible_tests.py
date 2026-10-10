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
check('inside', clamp_value(5, 0, 10), 5)
print(f'RESULT {len(_failures)} failures / %d checks' % 1)
sys.exit(1 if _failures else 0)
