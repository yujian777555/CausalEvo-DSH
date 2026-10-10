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
check('zero', int_to_binary(0, 3), '000')
check('exact', int_to_binary(255, 8), '11111111')
check('pad', int_to_binary(1, 5), '00001')
check('two', int_to_binary(2, 2), '10')
check('eight', int_to_binary(8, 6), '001000')
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
