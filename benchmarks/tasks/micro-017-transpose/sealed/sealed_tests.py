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
check('wide', transpose([[1, 2, 3]]), [[1], [2], [3]])
check('tall', transpose([[1], [2], [3]]), [[1, 2, 3]])
check('rect', transpose([[1, 2, 3], [4, 5, 6]]), [[1, 4], [2, 5], [3, 6]])
check('one', transpose([[9]]), [[9]])
check('twobythree', transpose([[1, 2], [3, 4], [5, 6]]), [[1, 3, 5], [2, 4, 6]])
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
