import hashlib
import sys

def hex_digit(c):
    if '0' <= c <= '9': return ord(c) - 48
    if 'a' <= c <= 'f': return ord(c) - 87
    if 'A' <= c <= 'F': return ord(c) - 55
    return 0

def check_prefix(hash_hex, prefix, hex_len):
    for i in range(hex_len):
        hn = (hash_hex[i // 2] >> (4 * (1 - i % 2))) & 0xf
        if hn != hex_digit(prefix[i]):
            return False
    return True

def brute_force(base, prefix, range_min=0, range_max=None):
    hex_len = len(prefix)
    nonce = range_min
    while range_max is None or nonce < range_max:
        data = (base + str(nonce)).encode()
        h = hashlib.md5(data).digest()
        if check_prefix(h, prefix, hex_len):
            return nonce, h.hex()
        nonce += 1
    return None, None

if __name__ == '__main__':
    if len(sys.argv) < 3:
        print(f"Uso: {sys.argv[0]} <cadena> <prefijo> [min] [max]")
        sys.exit(1)

    base = sys.argv[1]
    prefix = sys.argv[2]
    range_min = int(sys.argv[3]) if len(sys.argv) > 3 else 0
    range_max = int(sys.argv[4]) if len(sys.argv) > 4 else None

    nonce, hash_str = brute_force(base, prefix, range_min, range_max)
    if nonce is not None:
        print(f"Nonce = {nonce}\nMD5(\"{base}{nonce}\") = {hash_str}")
    else:
        print("No encontrado")
