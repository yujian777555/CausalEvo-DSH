def dedup_adjacent(xs):
    out = []
    for x in xs:
        if not out or x != out[-1]:
            out.append(x)
    return out
