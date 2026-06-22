# Instrucciones de Ejecución de Tests

## Resumen de Archivos Creados

### Scripts de Test
- **`run_comprehensive_tests.py`**: Script completo para ejecutar tests en CPU y GPU
- **`run_cpu_tests.py`**: Script simplificado para ejecutar solo tests en CPU
- **`run_comparativa.py`**: Script existente para comparación básica
- **`run_comparativa_fair.py`**: Script existente para comparación equitativa
- **`run_prefix_bench.py`**: Script existente para benchmark de prefijos

### Archivos de Parámetros
- **`cpu/tests/test_parameters.json`**: Parámetros de tests para CPU
- **`gpu/tests/test_parameters.json`**: Parámetros de tests para GPU

### Documentación
- **`COMPARATIVA_CPU_GPU.md`**: Documento de comparación con plantillas de resultados

## Ejecución Rápida

### Tests CPU (Requiere solo Python)
```bash
cd benchmarks
python run_cpu_tests.py
```

### Tests GPU (Requiere CUDA y compilación)
```bash
cd gpu
make
cd ../benchmarks
python run_comprehensive_tests.py
```

### Tests Completos (CPU + GPU)
```bash
cd gpu
make
cd ../benchmarks
python run_comprehensive_tests.py
```

## Batería de Tests

La batería incluye 10 casos de prueba con diferentes combinaciones:

1. Prefijo corto "0" con base "hola"
2. Prefijo medio "00" con base "hola"  
3. Prefijo largo "000" con base "hola"
4. Base diferente "test" con prefijo "0"
5. Base largo "blockchain" con prefijo "0"
6. Base "mining" con prefijo medio "00"
7. Base corta "data" con prefijo largo "000"
8. Rango limitado 0-1M
9. Rango limitado 0-5M
10. Rango desplazado 1M-2M

## Resultados

Los resultados se guardan en:
- `benchmarks/resultados/cpu_test_results.json` (solo CPU)
- `benchmarks/resultados/test_results.json` (CPU + GPU)
