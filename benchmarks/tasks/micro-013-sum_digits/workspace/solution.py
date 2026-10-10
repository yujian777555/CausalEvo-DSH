def sum_digits(n):
    return sum(int(d) for d in str(n) if d.isdigit()) if n >= 0 else -1
