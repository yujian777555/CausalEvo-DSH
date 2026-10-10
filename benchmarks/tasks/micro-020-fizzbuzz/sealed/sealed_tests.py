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
check('fifteen', fizzbuzz(15), 'FizzBuzz')
check('five', fizzbuzz(5), 'Buzz')
check('plain', fizzbuzz(7), '7')
check('thirty', fizzbuzz(30), 'FizzBuzz')
check('one', fizzbuzz(1), '1')
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
