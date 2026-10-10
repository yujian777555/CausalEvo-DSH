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
check('case', is_palindrome('Level'), True)
check('not', is_palindrome('hello'), False)
check('empty', is_palindrome(''), True)
check('one', is_palindrome('Z'), True)
check('mixed', is_palindrome('AbBa'), True)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
