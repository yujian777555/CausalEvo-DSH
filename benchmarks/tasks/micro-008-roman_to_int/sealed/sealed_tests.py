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
check('iv', roman_to_int('IV'), 4)
check('ix', roman_to_int('IX'), 9)
check('xiv', roman_to_int('XIV'), 14)
check('xlii', roman_to_int('XLII'), 42)
check('xcix', roman_to_int('XCIX'), 99)
print(f'RESULT {len(_failures)} failures / %d checks' % 5)
sys.exit(1 if _failures else 0)
