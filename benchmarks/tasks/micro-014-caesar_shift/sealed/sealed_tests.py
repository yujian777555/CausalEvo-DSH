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
check('wrap', caesar_shift('z', 1), 'a')
check('zero', caesar_shift('abc', 0), 'abc')
check('k13', caesar_shift('abc', 13), 'nop')
check('k25', caesar_shift('ab', 25), 'za')
check('full', caesar_shift('xyz', 3), 'abc')
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
