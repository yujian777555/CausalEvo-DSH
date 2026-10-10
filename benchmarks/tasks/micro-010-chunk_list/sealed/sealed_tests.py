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
check('tail', chunk_list([1, 2, 3], 2), [[1, 2], [3]])
check('n1', chunk_list([1, 2], 1), [[1], [2]])
check('big_n', chunk_list([1, 2], 5), [[1, 2]])
check('empty', chunk_list([], 3), [])
check('count', len(chunk_list(list(range(10)), 3)), 4)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
