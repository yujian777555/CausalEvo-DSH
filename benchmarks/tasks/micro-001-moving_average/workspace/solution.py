def moving_average(xs, k):
    return [sum(xs[i:i+k]) / k for i in range(len(xs) - k)]
