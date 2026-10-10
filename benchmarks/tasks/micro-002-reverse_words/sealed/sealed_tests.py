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
check('single', reverse_words('hello'), 'hello')
check('two', reverse_words('a b'), 'b a')
check('extra_spaces', reverse_words('  a   b  '), 'b a')
check('four', reverse_words('1 2 3 4'), '4 3 2 1')
check('case', reverse_words('Ab cD'), 'cD Ab')
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
