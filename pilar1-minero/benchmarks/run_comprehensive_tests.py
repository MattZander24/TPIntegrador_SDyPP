#!/usr/bin/env python3
"""
Batería de tests comprehensiva para comparar rendimiento CPU vs GPU
en minería Proof of Work con diferentes parámetros de entrada.
"""

import subprocess
import time
import sys
import os
from datetime import datetime

# Configuración de paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPU_SCRIPT = os.path.join(BASE_DIR, "cpu", "src", "brute_force.py")
GPU_BIN_DIR = os.path.join(BASE_DIR, "gpu", "bin")
GPU_BIN = os.path.join(GPU_BIN_DIR, "04_brute_force") if os.path.exists(GPU_BIN_DIR) else None
GPU_RANGE_BIN = os.path.join(GPU_BIN_DIR, "05_brute_force_range") if os.path.exists(GPU_BIN_DIR) else None

# Configuración de timeouts
GPU_TIMEOUT = 120
CPU_TIMEOUT = 300

# Batería de tests: diferentes combinaciones de parámetros
TEST_CASES = [
    # (base_string, prefix, range_min, range_max, description)
    ("hola", "0", 0, None, "Caso base: prefijo corto '0'"),
    ("hola", "00", 0, None, "Prefijo medio '00'"),
    ("hola", "000", 0, None, "Prefijo largo '000'"),
    ("test", "0", 0, None, "Base string diferente 'test'"),
    ("blockchain", "0", 0, None, "Base string largo 'blockchain'"),
    ("mining", "00", 0, None, "Base 'mining' con prefijo medio"),
    ("data", "000", 0, None, "Base corta con prefijo largo"),
    ("hola", "0", 0, 1000000, "Rango limitado 0-1M"),
    ("hola", "00", 0, 5000000, "Rango limitado 0-5M"),
    ("proof", "0", 1000000, 2000000, "Rango desplazado 1M-2M"),
]

def run_cpu_test(base, prefix, range_min=0, range_max=None):
    """Ejecuta test en CPU usando el script Python"""
    cmd = ["python", CPU_SCRIPT, base, prefix, str(range_min)]
    if range_max is not None:
        cmd.append(str(range_max))
    
    start = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=CPU_TIMEOUT)
        elapsed = time.time() - start
        
        # Extraer nonce del output
        nonce = None
        hash_result = None
        for line in result.stdout.split('\n'):
            if 'Nonce' in line:
                nonce = int(line.split('= ')[1])
            if 'MD5' in line:
                hash_result = line.split('= ')[1]
        
        return {
            'success': True,
            'nonce': nonce,
            'hash': hash_result,
            'time': elapsed,
            'output': result.stdout
        }
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {
            'success': False,
            'nonce': None,
            'hash': None,
            'time': elapsed,
            'output': f"Timeout después de {CPU_TIMEOUT}s"
        }
    except Exception as e:
        return {
            'success': False,
            'nonce': None,
            'hash': None,
            'time': 0,
            'output': f"Error: {str(e)}"
        }

def run_gpu_test(base, prefix, range_min=0, range_max=None):
    """Ejecuta test en GPU usando el binario CUDA"""
    if GPU_BIN is None:
        return {
            'success': False,
            'nonce': None,
            'hash': None,
            'time': 0,
            'output': "GPU binary no encontrado. Ejecuta 'make' en el directorio gpu/"
        }
    
    cmd = [GPU_BIN, base, prefix]
    
    start = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=GPU_TIMEOUT)
        elapsed = time.time() - start
        
        # Extraer nonce del output
        nonce = None
        hash_result = None
        for line in result.stdout.split('\n'):
            if 'Nonce' in line:
                nonce = int(line.split('= ')[1])
            if 'MD5' in line:
                hash_result = line.split('= ')[1]
        
        return {
            'success': True,
            'nonce': nonce,
            'hash': hash_result,
            'time': elapsed,
            'output': result.stdout
        }
    except subprocess.TimeoutExpired:
        elapsed = time.time() - start
        return {
            'success': False,
            'nonce': None,
            'hash': None,
            'time': elapsed,
            'output': f"Timeout después de {GPU_TIMEOUT}s"
        }
    except Exception as e:
        return {
            'success': False,
            'nonce': None,
            'hash': None,
            'time': 0,
            'output': f"Error: {str(e)}"
        }

def calculate_hash_rate(nonce, time_seconds):
    """Calcula tasa de hashes por segundo"""
    if nonce is None or time_seconds == 0:
        return 0
    return nonce / time_seconds

def main():
    print("="*80)
    print("BATERÍA DE TESTS COMPREHENSIVA CPU vs GPU")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    results = []
    
    for i, (base, prefix, range_min, range_max, description) in enumerate(TEST_CASES, 1):
        print(f"\n{'='*80}")
        print(f"Test #{i}: {description}")
        print(f"Parámetros: base='{base}', prefix='{prefix}', range=[{range_min}, {range_max if range_max else '∞'}]")
        print(f"{'='*80}")
        
        # Ejecutar test CPU
        print("\n--- CPU ---")
        cpu_result = run_cpu_test(base, prefix, range_min, range_max)
        print(f"Nonce: {cpu_result['nonce'] if cpu_result['nonce'] else 'No encontrado'}")
        print(f"Tiempo: {cpu_result['time']:.4f}s")
        cpu_rate = calculate_hash_rate(cpu_result['nonce'], cpu_result['time'])
        print(f"Hash rate: {cpu_rate:.2f} hashes/s")
        if not cpu_result['success']:
            print(f"Estado: {cpu_result['output']}")
        
        # Ejecutar test GPU
        print("\n--- GPU ---")
        gpu_result = run_gpu_test(base, prefix, range_min, range_max)
        print(f"Nonce: {gpu_result['nonce'] if gpu_result['nonce'] else 'No encontrado'}")
        print(f"Tiempo: {gpu_result['time']:.4f}s")
        gpu_rate = calculate_hash_rate(gpu_result['nonce'], gpu_result['time'])
        print(f"Hash rate: {gpu_rate:.2f} hashes/s")
        if not gpu_result['success']:
            print(f"Estado: {gpu_result['output']}")
        
        # Calcular speedup
        speedup = 0
        if cpu_rate > 0 and gpu_rate > 0:
            speedup = gpu_rate / cpu_rate
            print(f"\nSpeedup (GPU/CPU): {speedup:.2f}x")
        
        results.append({
            'test_id': i,
            'description': description,
            'base': base,
            'prefix': prefix,
            'range_min': range_min,
            'range_max': range_max,
            'cpu': cpu_result,
            'gpu': gpu_result,
            'cpu_rate': cpu_rate,
            'gpu_rate': gpu_rate,
            'speedup': speedup
        })
    
    # Imprimir resumen
    print(f"\n\n{'='*80}")
    print("RESUMEN COMPARATIVO")
    print(f"{'='*80}")
    print(f"{'#':>3} | {'Descripción':<30} | {'CPU Time':>10} | {'GPU Time':>10} | {'Speedup':>8}")
    print("-"*80)
    
    for r in results:
        desc = r['description'][:28] + '..' if len(r['description']) > 30 else r['description']
        cpu_time = f"{r['cpu']['time']:.2f}s" if r['cpu']['success'] else "TIMEOUT"
        gpu_time = f"{r['gpu']['time']:.2f}s" if r['gpu']['success'] else "N/A"
        speedup = f"{r['speedup']:.2f}x" if r['speedup'] > 0 else "-"
        print(f"{r['test_id']:>3} | {desc:<30} | {cpu_time:>10} | {gpu_time:>10} | {speedup:>8}")
    
    # Guardar resultados en archivo para procesamiento posterior
    import json
    output_file = os.path.join(os.path.dirname(__file__), "resultados", "test_results.json")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResultados guardados en: {output_file}")
    print("\nPruebas completadas.")

if __name__ == '__main__':
    main()
