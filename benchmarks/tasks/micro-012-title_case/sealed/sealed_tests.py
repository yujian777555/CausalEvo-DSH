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
check('upper', title_case('hELLO wORLD'), 'Hello World')
check('one', title_case('x'), 'X')
check('three', title_case('a b c'), 'A B C')
check('already', title_case('Ab Cd'), 'Ab Cd')
check('empty_word', title_case('a  b'), 'A  B')
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
