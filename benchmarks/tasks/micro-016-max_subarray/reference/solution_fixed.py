def max_subarray(xs):
    best = xs[0]
    cur = xs[0]
    for x in xs[1:]:
        cur = max(x, cur + x)
        best = max(best, cur)
    return best
