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
check('two', parse_kv('a=1;b=2'), {'a': '1', 'b': '2'})
check('eq_value', parse_kv('a=x=y'), {'a': 'x=y'})
check('mixed', parse_kv('k1=v;k2=a=b'), {'k1': 'v', 'k2': 'a=b'})
check('empty_value', parse_kv('a='), {'a': ''})
check('len_check', len(parse_kv('a=1;b=2;c=3')), 3)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
