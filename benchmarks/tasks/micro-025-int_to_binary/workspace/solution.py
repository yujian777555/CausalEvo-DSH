def int_to_binary(n, width):
    return bin(n)[2:].ljust(width, '0')
