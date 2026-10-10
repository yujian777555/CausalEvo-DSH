def caesar_shift(s, k):
    return ''.join(chr((ord(c) - 97 + k) % 26 + 97) for c in s)
