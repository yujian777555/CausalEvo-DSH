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
check('double_space', word_count('a  b'), 2)
check('empty', word_count(''), 0)
check('spaces_only', word_count('   '), 0)
check('tabs', word_count('a\tb'), 2)
check('edges', word_count('  a b  '), 2)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
