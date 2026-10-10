def balanced_parens(s):
    depth = 0
    for c in s:
        depth += 1 if c == '(' else -1
    return depth == 0
