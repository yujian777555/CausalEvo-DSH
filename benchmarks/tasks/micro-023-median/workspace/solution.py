def median(xs):
    s = sorted(xs)
    n = len(s)
    return float(s[n // 2])
