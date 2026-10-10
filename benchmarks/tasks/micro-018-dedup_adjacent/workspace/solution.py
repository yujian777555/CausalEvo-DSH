def dedup_adjacent(xs):
    out = []
    for i, x in enumerate(xs):
        if i == 0 or xs[i] != xs[0]:
            out.append(x)
    return out
