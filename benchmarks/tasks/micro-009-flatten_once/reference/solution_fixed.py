def flatten_once(lst):
    out = []
    for sub in lst:
        out.extend(sub)
    return out
