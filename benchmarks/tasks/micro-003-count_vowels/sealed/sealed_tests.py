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
check('with_y', count_vowels('gypsy'), 0)
check('upper', count_vowels('AEIOU'), 5)
check('empty', count_vowels(''), 0)
check('none', count_vowels('bcdfg'), 0)
check('mixed', count_vowels('PyThOn'), 1)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
