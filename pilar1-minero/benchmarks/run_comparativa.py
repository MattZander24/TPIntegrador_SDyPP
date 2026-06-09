#!/usr/bin/env python3
import subprocess
import time
import sys

GPU_BIN = "./brute"
CPU_SCRIPT = "python3 ../cpu/src/brute_force.py"
BASE = "hola"
PREFIXES = ["0", "00", "000"]
GPU_TIMEOUT = 120
CPU_TIMEOUT = 300

results = []

for prefix in PREFIXES:
    print(f"\n{'='*60}")
    print(f"Prefijo: '{prefix}' ({len(prefix)} hex chars)")
    print(f"{'='*60}")

    # GPU
    print(f"\n--- GPU (Tesla T4) ---")
    start = time.time()
    try:
        out = subprocess.run(
            [GPU_BIN, BASE, prefix],
            capture_output=True, text=True, timeout=GPU_TIMEOUT
        )
        gpu_time = time.time() - start
        gpu_nonce = None
        for line in out.stdout.split('\n'):
            if 'Nonce' in line:
                gpu_nonce = int(line.split('= ')[1])
        print(out.stdout.strip())
        print(f"Tiempo: {gpu_time:.4f}s")
    except subprocess.TimeoutExpired:
        gpu_time = GPU_TIMEOUT
        gpu_nonce = None
        print(f"Timeout ({GPU_TIMEOUT}s)")

    # CPU
    print(f"\n--- CPU (Python + hashlib) ---")
    start = time.time()
    try:
        out = subprocess.run(
            ["python3", "../cpu/src/brute_force.py", BASE, prefix],
            capture_output=True, text=True, timeout=CPU_TIMEOUT
        )
        cpu_time = time.time() - start
        cpu_nonce = None
        for line in out.stdout.split('\n'):
            if 'Nonce' in line:
                cpu_nonce = int(line.split('= ')[1])
        print(out.stdout.strip())
        print(f"Tiempo: {cpu_time:.4f}s")
    except subprocess.TimeoutExpired:
        cpu_time = CPU_TIMEOUT
        cpu_nonce = None
        print(f"Timeout ({CPU_TIMEOUT}s)")

    results.append((len(prefix), gpu_nonce, gpu_time, cpu_nonce, cpu_time))

print(f"\n\n{'='*70}")
print(f"{'RESUMEN COMPARATIVO':^70}")
print(f"{'='*70}")
print(f"{'Hex':>5} | {'GPU nonce':>12} | {'GPU time':>10} | {'CPU nonce':>12} | {'CPU time':>10} | {'Speedup':>8}")
print("-"*70)
for chars, gpu_n, gpu_t, cpu_n, cpu_t in results:
    gn = str(gpu_n) if gpu_n else "-"
    cn = str(cpu_n) if cpu_n else "-"
    speedup = f"{cpu_t/gpu_t:.1f}x" if gpu_t and cpu_n else "-"
    print(f"{chars:>5} | {gn:>12} | {gpu_t:>10.4f} | {cn:>12} | {cpu_t:>10.4f} | {speedup:>8}")
