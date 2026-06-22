#!/usr/bin/env python3
"""
Script simplificado para ejecutar tests solo en CPU
"""

import subprocess
import time
import sys
import os
import json
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CPU_SCRIPT = os.path.join(BASE_DIR, "cpu", "src", "brute_force.py")
CPU_TIMEOUT = 300

TEST_CASES = [
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
    cmd = ["python", CPU_SCRIPT, base, prefix, str(range_min)]
    if range_max is not None:
        cmd.append(str(range_max))
    
    start = time.time()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=CPU_TIMEOUT)
        elapsed = time.time() - start
        
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

def main():
    print("="*80)
    print("TESTS CPU - MINERÍA PROOF OF WORK")
    print(f"Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*80)
    
    results = []
    
    for i, (base, prefix, range_min, range_max, description) in enumerate(TEST_CASES, 1):
        print(f"\nTest #{i}: {description}")
        print(f"Parámetros: base='{base}', prefix='{prefix}', range=[{range_min}, {range_max if range_max else '∞'}]")
        
        cpu_result = run_cpu_test(base, prefix, range_min, range_max)
        
        print(f"Nonce: {cpu_result['nonce'] if cpu_result['nonce'] else 'No encontrado'}")
        print(f"Tiempo: {cpu_result['time']:.4f}s")
        
        if cpu_result['nonce'] and cpu_result['time'] > 0:
            rate = cpu_result['nonce'] / cpu_result['time']
            print(f"Hash rate: {rate:.2f} hashes/s")
        
        if not cpu_result['success']:
            print(f"Estado: {cpu_result['output']}")
        
        results.append({
            'test_id': i,
            'description': description,
            'base': base,
            'prefix': prefix,
            'range_min': range_min,
            'range_max': range_max,
            'cpu': cpu_result
        })
    
    print(f"\n\n{'='*80}")
    print("RESUMEN CPU")
    print(f"{'='*80}")
    print(f"{'#':>3} | {'Descripción':<30} | {'Nonce':>10} | {'Tiempo':>10} | {'Hash Rate':>12}")
    print("-"*80)
    
    for r in results:
        desc = r['description'][:28] + '..' if len(r['description']) > 30 else r['description']
        nonce = str(r['cpu']['nonce']) if r['cpu']['nonce'] else "N/A"
        time_str = f"{r['cpu']['time']:.4f}s" if r['cpu']['success'] else "TIMEOUT"
        
        if r['cpu']['nonce'] and r['cpu']['time'] > 0:
            rate = f"{r['cpu']['nonce']/r['cpu']['time']:.2f} H/s"
        else:
            rate = "N/A"
        
        print(f"{r['test_id']:>3} | {desc:<30} | {nonce:>10} | {time_str:>10} | {rate:>12}")
    
    output_file = os.path.join(os.path.dirname(__file__), "resultados", "cpu_test_results.json")
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2)
    
    print(f"\nResultados guardados en: {output_file}")

if __name__ == '__main__':
    main()
