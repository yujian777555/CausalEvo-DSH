"""Deterministic generator for the 24 Phase 1 microtasks.

Regeneration with the same seed MUST reproduce a byte-identical tree; the
registry pins every file hash and a test enforces it. Tasks are engineering
smoke fixtures ONLY — not evidence of external benchmark performance.
"""

from __future__ import annotations

import hashlib
import json
import random
import shutil
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TASKS_DIR = REPO_ROOT / "benchmarks" / "tasks"
REGISTRY_PATH = REPO_ROOT / "benchmarks" / "registry.json"
SPLIT_SEED = 20261010
SPLIT_QUOTA = {"train": 13, "dev": 7, "sealed_test": 6}

# Each spec: distinct function AND distinct bug class (dedup audit enforced by tests).
# checks are (test_name, expression-string evaluated against module namespace, expected).
TASKS = [
    dict(
        name="clamp_value", bug_class="swapped-arguments",
        instructions="solution.py provides clamp_value(x, lo, hi) that should clamp x into [lo, hi]. It is buggy. Fix it.",
        buggy="def clamp_value(x, lo, hi):\n    return min(max(x, hi), lo)\n",
        fixed="def clamp_value(x, lo, hi):\n    return min(max(x, lo), hi)\n",
        visible=[("inside", "clamp_value(5, 0, 10)", 5)],
        sealed=[("below", "clamp_value(-3, 0, 10)", 0), ("above", "clamp_value(99, 0, 10)", 10),
                ("at_lo", "clamp_value(0, 0, 10)", 0), ("at_hi", "clamp_value(10, 0, 10)", 10),
                ("float", "clamp_value(2.5, 0.0, 2.0)", 2.0)],
    ),
    dict(
        name="moving_average", bug_class="off-by-one",
        instructions="solution.py provides moving_average(xs, k): list of windowed means for every consecutive window of size k. It is buggy. Fix it.",
        buggy="def moving_average(xs, k):\n    return [sum(xs[i:i+k]) / k for i in range(len(xs) - k)]\n",
        fixed="def moving_average(xs, k):\n    return [sum(xs[i:i+k]) / k for i in range(len(xs) - k + 1)]\n",
        visible=[("two_windows", "moving_average([1.0, 2.0, 3.0], 2)", [1.5, 2.5])],
        sealed=[("single", "moving_average([1.0, 2.0], 1)", [1.0, 2.0]),
                ("full", "moving_average([2.0, 4.0], 2)", [3.0]),
                ("three", "moving_average([0.0, 3.0, 3.0, 6.0], 3)", [2.0, 4.0]),
                ("length", "len(moving_average([1.0]*10, 4))", 7),
                ("exact", "moving_average([5.0], 1)", [5.0])],
    ),
    dict(
        name="reverse_words", bug_class="missing-operation",
        instructions="solution.py provides reverse_words(s): reverse the order of whitespace-separated words. It is buggy. Fix it.",
        buggy="def reverse_words(s):\n    return ' '.join(s.split())\n",
        fixed="def reverse_words(s):\n    return ' '.join(reversed(s.split()))\n",
        visible=[("basic", "reverse_words('the quick fox')", "fox quick the")],
        sealed=[("single", "reverse_words('hello')", "hello"),
                ("two", "reverse_words('a b')", "b a"),
                ("extra_spaces", "reverse_words('  a   b  ')", "b a"),
                ("four", "reverse_words('1 2 3 4')", "4 3 2 1"),
                ("case", "reverse_words('Ab cD')", "cD Ab")],
    ),
    dict(
        name="count_vowels", bug_class="wrong-constant",
        instructions="solution.py provides count_vowels(s): count English vowels a,e,i,o,u (case-insensitive; y is NOT a vowel). It is buggy. Fix it.",
        buggy="def count_vowels(s):\n    return sum(1 for c in s.lower() if c in 'aeiouy')\n",
        fixed="def count_vowels(s):\n    return sum(1 for c in s.lower() if c in 'aeiou')\n",
        visible=[("basic", "count_vowels('apple')", 2)],
        sealed=[("with_y", "count_vowels('gypsy')", 0), ("upper", "count_vowels('AEIOU')", 5),
                ("empty", "count_vowels('')", 0), ("none", "count_vowels('bcdfg')", 0),
                ("mixed", "count_vowels('PyThOn')", 1)],
    ),
    dict(
        name="fibonacci", bug_class="wrong-base-case",
        instructions="solution.py provides fibonacci(n): n-th Fibonacci number with fibonacci(0)==0, fibonacci(1)==1. It is buggy. Fix it.",
        buggy="def fibonacci(n):\n    if n <= 1:\n        return 1\n    a, b = 1, 1\n    for _ in range(n - 1):\n        a, b = b, a + b\n    return a\n",
        fixed="def fibonacci(n):\n    if n <= 1:\n        return n\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n",
        visible=[("fib5", "fibonacci(5)", 5)],
        sealed=[("fib0", "fibonacci(0)", 0), ("fib1", "fibonacci(1)", 1),
                ("fib2", "fibonacci(2)", 1), ("fib10", "fibonacci(10)", 55),
                ("fib15", "fibonacci(15)", 610)],
    ),
    dict(
        name="merge_sorted", bug_class="inverted-comparison",
        instructions="solution.py provides merge_sorted(a, b): merge two ascending lists into one ascending list. It is buggy. Fix it.",
        buggy="def merge_sorted(a, b):\n    out = []\n    i = j = 0\n    while i < len(a) and j < len(b):\n        if a[i] >= b[j]:\n            out.append(a[i]); i += 1\n        else:\n            out.append(b[j]); j += 1\n    out.extend(a[i:]); out.extend(b[j:])\n    return out\n",
        fixed="def merge_sorted(a, b):\n    out = []\n    i = j = 0\n    while i < len(a) and j < len(b):\n        if a[i] <= b[j]:\n            out.append(a[i]); i += 1\n        else:\n            out.append(b[j]); j += 1\n    out.extend(a[i:]); out.extend(b[j:])\n    return out\n",
        visible=[("basic", "merge_sorted([1, 3], [2, 4])", [1, 2, 3, 4])],
        sealed=[("empty_left", "merge_sorted([], [1])", [1]),
                ("empty_right", "merge_sorted([1], [])", [1]),
                ("interleave", "merge_sorted([1, 5, 9], [2, 3, 10])", [1, 2, 3, 5, 9, 10]),
                ("dup", "merge_sorted([1, 1], [1])", [1, 1, 1]),
                ("neg", "merge_sorted([-5, 0], [-3])", [-5, -3, 0])],
    ),
    dict(
        name="is_palindrome", bug_class="missing-normalization",
        instructions="solution.py provides is_palindrome(s): True iff s reads the same forwards and backwards, case-insensitively. It is buggy. Fix it.",
        buggy="def is_palindrome(s):\n    return s == s[::-1]\n",
        fixed="def is_palindrome(s):\n    return s.lower() == s.lower()[::-1]\n",
        visible=[("basic", "is_palindrome('level')", True)],
        sealed=[("case", "is_palindrome('Level')", True), ("not", "is_palindrome('hello')", False),
                ("empty", "is_palindrome('')", True), ("one", "is_palindrome('Z')", True),
                ("mixed", "is_palindrome('AbBa')", True)],
    ),
    dict(
        name="binary_search", bug_class="wrong-return",
        instructions="solution.py provides binary_search(xs, t): index of t in ascending xs, or -1 if absent. It is buggy. Fix it.",
        buggy="def binary_search(xs, t):\n    lo, hi = 0, len(xs) - 1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if xs[mid] == t:\n            return mid\n        if xs[mid] < t:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n    return lo\n",
        fixed="def binary_search(xs, t):\n    lo, hi = 0, len(xs) - 1\n    while lo <= hi:\n        mid = (lo + hi) // 2\n        if xs[mid] == t:\n            return mid\n        if xs[mid] < t:\n            lo = mid + 1\n        else:\n            hi = mid - 1\n    return -1\n",
        visible=[("found", "binary_search([1, 3, 5, 7], 5)", 2)],
        sealed=[("absent", "binary_search([1, 3, 5], 4)", -1),
                ("first", "binary_search([1, 3, 5], 1)", 0),
                ("last", "binary_search([1, 3, 5], 5)", 2),
                ("empty", "binary_search([], 1)", -1),
                ("absent_high", "binary_search([1, 2], 99)", -1)],
    ),
    dict(
        name="roman_to_int", bug_class="inverted-condition",
        instructions="solution.py provides roman_to_int(s): convert a valid Roman numeral (I,V,X,L,C) to int, standard subtraction rule. It is buggy. Fix it.",
        buggy="def roman_to_int(s):\n    vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}\n    total = 0\n    for i, ch in enumerate(s):\n        if i + 1 < len(s) and vals[ch] >= vals[s[i + 1]]:\n            total -= vals[ch]\n        else:\n            total += vals[ch]\n    return total\n",
        fixed="def roman_to_int(s):\n    vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}\n    total = 0\n    for i, ch in enumerate(s):\n        if i + 1 < len(s) and vals[ch] < vals[s[i + 1]]:\n            total -= vals[ch]\n        else:\n            total += vals[ch]\n    return total\n",
        visible=[("vi", "roman_to_int('VI')", 6)],
        sealed=[("iv", "roman_to_int('IV')", 4), ("ix", "roman_to_int('IX')", 9),
                ("xiv", "roman_to_int('XIV')", 14), ("xlii", "roman_to_int('XLII')", 42),
                ("xcix", "roman_to_int('XCIX')", 99)],
    ),
    dict(
        name="flatten_once", bug_class="wrong-iteration",
        instructions="solution.py provides flatten_once(lst): flatten one nesting level, e.g. [[1,2],[3]] -> [1,2,3]. It is buggy. Fix it.",
        buggy="def flatten_once(lst):\n    out = []\n    for sub in lst:\n        out.extend([sub])\n    return out\n",
        fixed="def flatten_once(lst):\n    out = []\n    for sub in lst:\n        out.extend(sub)\n    return out\n",
        visible=[("basic", "flatten_once([[1, 2], [3]])", [1, 2, 3])],
        sealed=[("empty", "flatten_once([])", []), ("empties", "flatten_once([[], []])", []),
                ("nested_kept", "flatten_once([[[1]], [2]])", [[1], 2]),
                ("single", "flatten_once([[7]])", [7]),
                ("strings", "flatten_once([['a'], ['b', 'c']])", ['a', 'b', 'c'])],
    ),
    dict(
        name="chunk_list", bug_class="missing-step",
        instructions="solution.py provides chunk_list(xs, n): split xs into consecutive chunks of size n (last chunk may be shorter). It is buggy. Fix it.",
        buggy="def chunk_list(xs, n):\n    return [xs[i:i + n] for i in range(0, len(xs))]\n",
        fixed="def chunk_list(xs, n):\n    return [xs[i:i + n] for i in range(0, len(xs), n)]\n",
        visible=[("pairs", "chunk_list([1, 2, 3, 4], 2)", [[1, 2], [3, 4]])],
        sealed=[("tail", "chunk_list([1, 2, 3], 2)", [[1, 2], [3]]),
                ("n1", "chunk_list([1, 2], 1)", [[1], [2]]),
                ("big_n", "chunk_list([1, 2], 5)", [[1, 2]]),
                ("empty", "chunk_list([], 3)", []),
                ("count", "len(chunk_list(list(range(10)), 3))", 4)],
    ),
    dict(
        name="second_largest", bug_class="wrong-end",
        instructions="solution.py provides second_largest(xs): the second-largest distinct value in xs (xs has >=2 distinct values). It is buggy. Fix it.",
        buggy="def second_largest(xs):\n    return sorted(set(xs))[1]\n",
        fixed="def second_largest(xs):\n    return sorted(set(xs))[-2]\n",
        visible=[("basic", "second_largest([1, 5, 3])", 3)],
        sealed=[("two", "second_largest([10, 20])", 10),
                ("dups", "second_largest([5, 5, 9, 9, 2])", 5),
                ("neg", "second_largest([-1, -5, -3])", -3),
                ("sorted", "second_largest([1, 2, 3, 4])", 3),
                ("reverse", "second_largest([4, 3, 2, 1])", 3)],
    ),
    dict(
        name="title_case", bug_class="incomplete-mapping",
        instructions="solution.py provides title_case(s): capitalize the first letter of every whitespace-separated word, lowercase the rest. It is buggy. Fix it.",
        buggy="def title_case(s):\n    return s.capitalize()\n",
        fixed="def title_case(s):\n    return ' '.join(w.capitalize() for w in s.split(' '))\n",
        visible=[("basic", "title_case('hello world')", "Hello World")],
        sealed=[("upper", "title_case('hELLO wORLD')", "Hello World"),
                ("one", "title_case('x')", "X"),
                ("three", "title_case('a b c')", "A B C"),
                ("already", "title_case('Ab Cd')", "Ab Cd"),
                ("empty_word", "title_case('a  b')", "A  B")],
    ),
    dict(
        name="sum_digits", bug_class="missing-edge-case",
        instructions="solution.py provides sum_digits(n): sum of decimal digits of integer n, also correct for negative n (sign ignored). It is buggy. Fix it.",
        buggy="def sum_digits(n):\n    return sum(int(d) for d in str(n) if d.isdigit()) if n >= 0 else -1\n",
        fixed="def sum_digits(n):\n    return sum(int(d) for d in str(abs(n)))\n",
        visible=[("basic", "sum_digits(123)", 6)],
        sealed=[("neg", "sum_digits(-123)", 6), ("zero", "sum_digits(0)", 0),
                ("neg_zero", "sum_digits(-5)", 5), ("big", "sum_digits(9999)", 36),
                ("ten", "sum_digits(10)", 1)],
    ),
    dict(
        name="caesar_shift", bug_class="wrong-direction",
        instructions="solution.py provides caesar_shift(s, k): shift every lowercase ASCII letter FORWARD by k positions (wrap around). It is buggy. Fix it.",
        buggy="def caesar_shift(s, k):\n    return ''.join(chr((ord(c) - 97 - k) % 26 + 97) for c in s)\n",
        fixed="def caesar_shift(s, k):\n    return ''.join(chr((ord(c) - 97 + k) % 26 + 97) for c in s)\n",
        visible=[("basic", "caesar_shift('abc', 1)", "bcd")],
        sealed=[("wrap", "caesar_shift('z', 1)", "a"), ("zero", "caesar_shift('abc', 0)", "abc"),
                ("k13", "caesar_shift('abc', 13)", "nop"), ("k25", "caesar_shift('ab', 25)", "za"),
                ("full", "caesar_shift('xyz', 3)", "abc")],
    ),
    dict(
        name="balanced_parens", bug_class="missing-prefix-check",
        instructions="solution.py provides balanced_parens(s): True iff parentheses string s is balanced (never negative prefix, ends at zero). It is buggy. Fix it.",
        buggy="def balanced_parens(s):\n    depth = 0\n    for c in s:\n        depth += 1 if c == '(' else -1\n    return depth == 0\n",
        fixed="def balanced_parens(s):\n    depth = 0\n    for c in s:\n        depth += 1 if c == '(' else -1\n        if depth < 0:\n            return False\n    return depth == 0\n",
        visible=[("basic", "balanced_parens('(())')", True)],
        sealed=[("prefix", "balanced_parens(')(')", False), ("open", "balanced_parens('(')", False),
                ("close", "balanced_parens(')')", False), ("nested", "balanced_parens('(()())')", True),
                ("late_bad", "balanced_parens('()( )('.replace(' ', ''))", False)],
    ),
    dict(
        name="max_subarray", bug_class="wrong-initial-value",
        instructions="solution.py provides max_subarray(xs): maximum sum of any non-empty contiguous subarray (Kadane). It is buggy. Fix it.",
        buggy="def max_subarray(xs):\n    best = 0\n    cur = 0\n    for x in xs:\n        cur = max(0, cur + x)\n        best = max(best, cur)\n    return best\n",
        fixed="def max_subarray(xs):\n    best = xs[0]\n    cur = xs[0]\n    for x in xs[1:]:\n        cur = max(x, cur + x)\n        best = max(best, cur)\n    return best\n",
        visible=[("basic", "max_subarray([1, -2, 3, 4, -1])", 7)],
        sealed=[("all_neg", "max_subarray([-5, -2, -9])", -2),
                ("single", "max_subarray([-7])", -7),
                ("all_pos", "max_subarray([1, 2, 3])", 6),
                ("mixed", "max_subarray([2, -1, 2])", 3),
                ("zero", "max_subarray([0, -1, 0])", 0)],
    ),
    dict(
        name="transpose", bug_class="swapped-indices",
        instructions="solution.py provides transpose(m): transpose a rectangular matrix (list of rows). It is buggy. Fix it.",
        buggy="def transpose(m):\n    return [[m[i][j] for i in range(len(m))] for j in range(len(m))]\n",
        fixed="def transpose(m):\n    return [[m[i][j] for i in range(len(m))] for j in range(len(m[0]))]\n",
        visible=[("square", "transpose([[1, 2], [3, 4]])", [[1, 3], [2, 4]])],
        sealed=[("wide", "transpose([[1, 2, 3]])", [[1], [2], [3]]),
                ("tall", "transpose([[1], [2], [3]])", [[1, 2, 3]]),
                ("rect", "transpose([[1, 2, 3], [4, 5, 6]])", [[1, 4], [2, 5], [3, 6]]),
                ("one", "transpose([[9]])", [[9]]),
                ("twobythree", "transpose([[1, 2], [3, 4], [5, 6]])", [[1, 3, 5], [2, 4, 6]])],
    ),
    dict(
        name="dedup_adjacent", bug_class="wrong-comparison-target",
        instructions="solution.py provides dedup_adjacent(xs): remove consecutive duplicates, keeping first of each run. It is buggy. Fix it.",
        buggy="def dedup_adjacent(xs):\n    out = []\n    for i, x in enumerate(xs):\n        if i == 0 or xs[i] != xs[0]:\n            out.append(x)\n    return out\n",
        fixed="def dedup_adjacent(xs):\n    out = []\n    for x in xs:\n        if not out or x != out[-1]:\n            out.append(x)\n    return out\n",
        visible=[("basic", "dedup_adjacent([1, 1, 2])", [1, 2])],
        sealed=[("runs", "dedup_adjacent([1, 1, 2, 2, 1])", [1, 2, 1]),
                ("all_same", "dedup_adjacent([3, 3, 3])", [3]),
                ("none_adj", "dedup_adjacent([1, 2, 1])", [1, 2, 1]),
                ("empty", "dedup_adjacent([])", []),
                ("mixed", "dedup_adjacent([0, 0, 1, 0, 0])", [0, 1, 0])],
    ),
    dict(
        name="parse_kv", bug_class="missing-limit",
        instructions="solution.py provides parse_kv(s): parse 'k=v;k2=v2' into a dict; values may contain '='. It is buggy. Fix it.",
        buggy="def parse_kv(s):\n    out = {}\n    for part in s.split(';'):\n        k, v = part.split('=')\n        out[k] = v\n    return out\n",
        fixed="def parse_kv(s):\n    out = {}\n    for part in s.split(';'):\n        k, v = part.split('=', 1)\n        out[k] = v\n    return out\n",
        visible=[("basic", "parse_kv('a=1')", {"a": "1"})],
        sealed=[("two", "parse_kv('a=1;b=2')", {"a": "1", "b": "2"}),
                ("eq_value", "parse_kv('a=x=y')", {"a": "x=y"}),
                ("mixed", "parse_kv('k1=v;k2=a=b')", {"k1": "v", "k2": "a=b"}),
                ("empty_value", "parse_kv('a=')", {"a": ""}),
                ("len_check", "len(parse_kv('a=1;b=2;c=3'))", 3)],
    ),
    dict(
        name="fizzbuzz", bug_class="wrong-order",
        instructions="solution.py provides fizzbuzz(n): 'FizzBuzz' if divisible by 15, 'Fizz' by 3, 'Buzz' by 5, else str(n). It is buggy. Fix it.",
        buggy="def fizzbuzz(n):\n    if n % 3 == 0:\n        return 'Fizz'\n    if n % 5 == 0:\n        return 'Buzz'\n    if n % 15 == 0:\n        return 'FizzBuzz'\n    return str(n)\n",
        fixed="def fizzbuzz(n):\n    if n % 15 == 0:\n        return 'FizzBuzz'\n    if n % 3 == 0:\n        return 'Fizz'\n    if n % 5 == 0:\n        return 'Buzz'\n    return str(n)\n",
        visible=[("three", "fizzbuzz(3)", "Fizz")],
        sealed=[("fifteen", "fizzbuzz(15)", "FizzBuzz"), ("five", "fizzbuzz(5)", "Buzz"),
                ("plain", "fizzbuzz(7)", "7"), ("thirty", "fizzbuzz(30)", "FizzBuzz"),
                ("one", "fizzbuzz(1)", "1")],
    ),
    dict(
        name="gcd", bug_class="wrong-final-value",
        instructions="solution.py provides gcd(a, b): greatest common divisor of positive integers via Euclid. It is buggy. Fix it.",
        buggy="def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return b\n",
        fixed="def gcd(a, b):\n    while b:\n        a, b = b, a % b\n    return a\n",
        visible=[("basic", "gcd(12, 8)", 4)],
        sealed=[("coprime", "gcd(7, 3)", 1), ("equal", "gcd(5, 5)", 5),
                ("one", "gcd(1, 9)", 1), ("big", "gcd(1071, 462)", 21),
                ("reversed", "gcd(8, 12)", 4)],
    ),
    dict(
        name="word_count", bug_class="naive-split",
        instructions="solution.py provides word_count(s): number of whitespace-separated words; runs of whitespace count as one separator. It is buggy. Fix it.",
        buggy="def word_count(s):\n    return len(s.split(' '))\n",
        fixed="def word_count(s):\n    return len(s.split())\n",
        visible=[("basic", "word_count('a b c')", 3)],
        sealed=[("double_space", "word_count('a  b')", 2), ("empty", "word_count('')", 0),
                ("spaces_only", "word_count('   ')", 0), ("tabs", "word_count('a\\tb')", 2),
                ("edges", "word_count('  a b  ')", 2)],
    ),
    dict(
        name="median", bug_class="missing-branch",
        instructions="solution.py provides median(xs): median of a non-empty list; even length -> mean of the two middle values. It is buggy. Fix it.",
        buggy="def median(xs):\n    s = sorted(xs)\n    n = len(s)\n    return float(s[n // 2])\n",
        fixed="def median(xs):\n    s = sorted(xs)\n    n = len(s)\n    mid = n // 2\n    if n % 2 == 1:\n        return float(s[mid])\n    return (s[mid - 1] + s[mid]) / 2\n",
        visible=[("odd", "median([3, 1, 2])", 2.0)],
        sealed=[("even", "median([1, 2, 3, 4])", 2.5), ("two", "median([1, 10])", 5.5),
                ("one", "median([7])", 7.0), ("unsorted", "median([9, 1, 5])", 5.0),
                ("even_neg", "median([-4, -2])", -3.0)],
    ),
    dict(
        name="count_inversions_naive", bug_class="inverted-strictness",
        instructions="solution.py provides count_inversions(xs): number of pairs i<j with xs[i] > xs[j] (strictly greater). It is buggy. Fix it.",
        buggy="def count_inversions(xs):\n    n = len(xs)\n    return sum(1 for i in range(n) for j in range(i + 1, n) if xs[i] >= xs[j])\n",
        fixed="def count_inversions(xs):\n    n = len(xs)\n    return sum(1 for i in range(n) for j in range(i + 1, n) if xs[i] > xs[j])\n",
        visible=[("basic", "count_inversions([2, 1])", 1)],
        sealed=[("sorted", "count_inversions([1, 2, 3])", 0),
                ("reverse", "count_inversions([3, 2, 1])", 3),
                ("equal", "count_inversions([2, 2])", 0),
                ("mixed", "count_inversions([1, 3, 2])", 1),
                ("empty", "count_inversions([])", 0)],
    ),
    dict(
        name="int_to_binary", bug_class="wrong-padding-side",
        instructions="solution.py provides int_to_binary(n, width): binary string of non-negative n zero-padded on the LEFT to width (n fits). It is buggy. Fix it.",
        buggy="def int_to_binary(n, width):\n    return bin(n)[2:].ljust(width, '0')\n",
        fixed="def int_to_binary(n, width):\n    return bin(n)[2:].rjust(width, '0')\n",
        visible=[("basic", "int_to_binary(5, 4)", "0101")],
        sealed=[("zero", "int_to_binary(0, 3)", "000"), ("exact", "int_to_binary(255, 8)", "11111111"),
                ("pad", "int_to_binary(1, 5)", "00001"), ("two", "int_to_binary(2, 2)", "10"),
                ("eight", "int_to_binary(8, 6)", "001000")],
    ),
]


def _write(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _test_script(module: str, checks: list) -> str:
    lines = [
        "import sys, pathlib",
        "sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))",
        f"from {module} import *  # noqa",
        "_failures = []",
        "def check(name, actual, expected):",
        "    if actual != expected:",
        "        _failures.append((name, actual, expected))",
        "        print(f'FAIL {name}: got {actual!r} want {expected!r}')",
        "    else:",
        "        print(f'PASS {name}')",
    ]
    for name, expr, expected in checks:
        lines.append(f"check({name!r}, {expr}, {expected!r})")
    lines += [
        "print(f'RESULT {len(_failures)} failures / %d checks' % " + str(len(checks)) + ")",
        "sys.exit(1 if _failures else 0)",
        "",
    ]
    return "\n".join(lines)


def _audit_bugs_actually_fail() -> None:
    """Authoring audit: every buggy solution must fail at least one sealed
    check, and every fixed reference must pass all of them. Catches tasks that
    silently pass with the bug in place (found once in practice: gcd)."""
    for spec in TASKS:
        ns_buggy: dict = {}
        exec(spec["buggy"], ns_buggy)
        failures = 0
        for _name, expr, expected in spec["sealed"]:
            try:
                if eval(expr, dict(ns_buggy)) != expected:
                    failures += 1
            except Exception:
                failures += 1  # an exception is also a failing check
        assert failures >= 1, f"{spec['name']}: buggy code passes all sealed checks"
        ns_fixed: dict = {}
        exec(spec["fixed"], ns_fixed)
        bad = []
        for name, expr, expected in spec["sealed"] + spec["visible"]:
            try:
                if eval(expr, dict(ns_fixed)) != expected:
                    bad.append(name)
            except Exception:
                bad.append(name)
        assert not bad, f"{spec['name']}: fixed reference fails checks {bad}"


def main() -> None:
    assert len({t["name"] for t in TASKS}) == 26, "function names must be unique"
    assert len({t["bug_class"] for t in TASKS}) == 26, "bug classes must be unique"
    _audit_bugs_actually_fail()

    order = [t["name"] for t in TASKS]
    rng = random.Random(SPLIT_SEED)
    rng.shuffle(order)
    split_of: dict[str, str] = {}
    idx = 0
    for split, quota in SPLIT_QUOTA.items():
        for name in order[idx:idx + quota]:
            split_of[name] = split
        idx += quota

    if TASKS_DIR.exists():
        shutil.rmtree(TASKS_DIR)
    registry_tasks = []
    for i, spec in enumerate(TASKS):
        task_id = f"micro-{i:03d}-{spec['name']}"
        split = split_of[spec["name"]]
        tdir = TASKS_DIR / task_id
        hashes = {}
        hashes["workspace/solution.py"] = _write(tdir / "workspace" / "solution.py", spec["buggy"])
        hashes["visible_tests.py"] = _write(
            tdir / "visible_tests.py", _test_script("solution", spec["visible"]))
        hashes["sealed/sealed_tests.py"] = _write(
            tdir / "sealed" / "sealed_tests.py", _test_script("solution", spec["sealed"]))
        hashes["reference/solution_fixed.py"] = _write(
            tdir / "reference" / "solution_fixed.py", spec["fixed"])
        task_meta = {
            "task_id": task_id,
            "function": spec["name"],
            "bug_class": spec["bug_class"],
            "split": split,
            "instructions": spec["instructions"],
            "entry_file": "solution.py",
            "timeout_s": 30,
            "n_visible_checks": len(spec["visible"]),
            "n_sealed_checks": len(spec["sealed"]),
            "hashes": hashes,
        }
        task_meta["task_json_sha256"] = hashlib.sha256(
            json.dumps(task_meta, sort_keys=True).encode("utf-8")
        ).hexdigest()
        _write(tdir / "task.json", json.dumps(task_meta, indent=2, ensure_ascii=False) + "\n")
        registry_tasks.append({
            "task_id": task_id, "split": split, "function": spec["name"],
            "bug_class": spec["bug_class"], "hashes": hashes,
        })

    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    registry["microtasks"] = {
        "count": len(registry_tasks),
        "purpose": "engineering smoke only; NOT external benchmark performance evidence",
        "split_seed": SPLIT_SEED,
        "split_quota": SPLIT_QUOTA,
        "splits": {
            split: sorted(t["task_id"] for t in registry_tasks if t["split"] == split)
            for split in SPLIT_QUOTA
        },
        "tasks": registry_tasks,
    }
    REGISTRY_PATH.write_text(
        json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"generated {len(registry_tasks)} tasks; splits:",
          {s: len(v) for s, v in registry["microtasks"]["splits"].items()})


if __name__ == "__main__":
    main()
