def balanced_parens(s):
    depth = 0
    for c in s:
        depth += 1 if c == '(' else -1
        if depth < 0:
            return False
    return depth == 0
