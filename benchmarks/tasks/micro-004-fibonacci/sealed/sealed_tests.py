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
check('fib0', fibonacci(0), 0)
check('fib1', fibonacci(1), 1)
check('fib2', fibonacci(2), 1)
check('fib10', fibonacci(10), 55)
check('fib15', fibonacci(15), 610)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
