def count_inversions(xs):
    n = len(xs)
    return sum(1 for i in range(n) for j in range(i + 1, n) if xs[i] > xs[j])
