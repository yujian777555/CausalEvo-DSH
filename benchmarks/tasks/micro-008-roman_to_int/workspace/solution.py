def roman_to_int(s):
    vals = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100}
    total = 0
    for i, ch in enumerate(s):
        if i + 1 < len(s) and vals[ch] >= vals[s[i + 1]]:
            total -= vals[ch]
        else:
            total += vals[ch]
    return total
