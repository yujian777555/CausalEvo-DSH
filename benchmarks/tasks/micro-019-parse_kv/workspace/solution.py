def parse_kv(s):
    out = {}
    for part in s.split(';'):
        k, v = part.split('=')
        out[k] = v
    return out
