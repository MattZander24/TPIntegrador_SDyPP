import subprocess, time

BASE = "hola"
PREFIXES_TIMES = {"0": 5, "00": 10, "000": 30}

for prefix, timeout in PREFIXES_TIMES.items():
    print(f"\n=== Prefijo '{prefix}' ===")

    # GPU (range, busca en [0, 5 millones) para tener corrida larga)
    start = time.time()
    gpu = subprocess.run(["./brute_range", BASE, prefix, "0", "5000000"],
                         capture_output=True, text=True, timeout=timeout)
    gt = time.time() - start
    gpu_nonce = next((int(l.split('= ')[1]) for l in gpu.stdout.split('\n') if 'Nonce' in l), None)
    gpu_hashes = (gpu_nonce // 65536 + 1) * 65536 if gpu_nonce else 0
    gpu_rate = gpu_hashes / gt / 1e6 if gt > 0 else 0
    print(f"[GPU] nonce={gpu_nonce}, tiempo={gt:.2f}s -> {gpu_rate:.1f} MHash/s")

    # CPU
    start = time.time()
    cpu = subprocess.run(["python3", "brute.py", BASE, prefix],
                         capture_output=True, text=True, timeout=120)
    ct = time.time() - start
    cpu_nonce = next((int(l.split('= ')[1]) for l in cpu.stdout.split('\n') if 'Nonce' in l), None)
    cpu_rate = cpu_nonce / ct / 1e6 if ct > 0 else 0
    print(f"[CPU] nonce={cpu_nonce}, tiempo={ct:.2f}s -> {cpu_rate:.3f} MHash/s")

    if gpu_rate > 0 and cpu_rate > 0:
        print(f"Speedup: {gpu_rate/cpu_rate:.0f}x")
