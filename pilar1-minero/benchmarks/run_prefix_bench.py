import subprocess
import time
import sys

BASE_STRING = "hola"
PREFIXES = ["0", "00", "000", "0000", "00000", "000000"]
TIMEOUT = 300

results = []

for prefix in PREFIXES:
    prob = 1.0 / (16 ** len(prefix))
    expected_nonces = int(1.0 / prob)

    print(f"\n=== Prefijo '{prefix}' ({len(prefix)} hex chars, 1/{16**len(prefix)}) ===")
    print(f"Nonces esperados hasta encontrar: ~{expected_nonces}")

    start = time.time()
    try:
        out = subprocess.run(
            ["./brute", BASE_STRING, prefix],
            capture_output=True, text=True, timeout=TIMEOUT
        )
        elapsed = time.time() - start
        print(out.stdout)
        if "Nonce" in out.stdout:
            nonce_line = [l for l in out.stdout.split('\n') if 'Nonce' in l][0]
            nonce = int(nonce_line.split('= ')[1])
            results.append((len(prefix), nonce, elapsed, expected_nonces))
        else:
            results.append((len(prefix), None, elapsed, expected_nonces))
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        print(f"Timeout ({TIMEOUT}s)")
        results.append((len(prefix), None, elapsed, expected_nonces))

print("\n\n=== RESUMEN ===")
print(f"{'Hex chars':>10} | {'Nonce':>15} | {'Tiempo (s)':>10} | {'Esperado':>15} | {'Ratio':>10}")
print("-" * 70)
for chars, nonce, elapsed, expected in results:
    ratio = nonce / expected if nonce else 0
    n = str(nonce) if nonce else "TIMEOUT"
    print(f"{chars:>10} | {n:>15} | {elapsed:>10.2f} | {expected:>15} | {ratio:>10.2f}")
