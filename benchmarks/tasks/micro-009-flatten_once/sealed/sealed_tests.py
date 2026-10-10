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
check('empty', flatten_once([]), [])
check('empties', flatten_once([[], []]), [])
check('nested_kept', flatten_once([[[1]], [2]]), [[1], 2])
check('single', flatten_once([[7]]), [7])
check('strings', flatten_once([['a'], ['b', 'c']]), ['a', 'b', 'c'])
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
