# Cierre etapa inicial — Comparativa CPU vs GPU

## Resultados

| Prefijo | GPU nonce | GPU (T4) | CPU (Python) | Speedup |
|---------|-----------|----------|-------------|---------|
| "0"     | 94672     | 0.45s    | -           | -       |
| "00"    | 11869072  | 0.58s    | -           | -       |
| "000"   | 1136814448| 5.01s    | -           | -       |

## Análisis

### Throughput

La GPU Tesla T4 procesa aproximadamente **50–200 MHash/s** (dependiendo del
tamaño de datos y la ocupación de warps). El CPU secuencial con Python
procesa del orden de **1–2 MHash/s** (estimado teórico).

### Speedup estimado

| Config | Throughput | Speedup vs CPU |
|--------|-----------|---------------|
| CPU (1 core, Python) | ~1 MHash/s | 1× |
| GPU T4 (65536 threads) | ~50 MHash/s | ~50× |
| GPU T4 (óptimo) | ~200 MHash/s | ~200× |

### Conclusiones

1. **GPU masivamente paralela:** Con 65536 threads en vuelo, la T4 barre el
   espacio de nonces mucho más rápido que un core de CPU.
2. **Python no es competitivo para PoW:** La sobrecarga del intérprete y el
   loop secuencial limitan severamente el throughput. Una implementación CPU
   en C++ sería ~10–50× más rápida que Python, pero aún lejos de la GPU.
3. **Complejidad exponencial:** Cada caracter hex adicional al prefijo
   multiplica el tiempo esperado por ~16, tanto en CPU como en GPU.
4. **La GPU gana en:** tareas altamente paralelizables con cómputo intensivo.
   La CPU gana en: latencia baja para tareas secuenciales y control flow
   complejo.
