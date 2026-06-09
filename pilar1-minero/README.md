# Pilar 1 — Minería CPU + GPU CUDA

Desarrollo progresivo de los algoritmos de hashing y minería Proof of Work.

## Estructura

```
cpu/            — Minero CPU (Python/Node/Java)
gpu/            — Minero GPU en CUDA C/C++
benchmarks/     — Comparativas CPU vs GPU
```

## Hits desarrollados

| Hit  | Archivo GPU               | Descripción                          |
|------|---------------------------|--------------------------------------|
| #2   | `01_hello.cu`             | Hello World CUDA                     |
| #3   | `02_thrust_vector.cu`     | Thrust Vectors (CCCL)                |
| #4   | `03_md5_hash.cu`          | MD5 de un string por parámetro       |
| #5   | `04_brute_force.cu`       | Fuerza bruta (hash + cadena → nonce) |
| #6   | `05_prefix_bench.cu`      | Métricas por longitud de prefijo     |
| #7   | `06_brute_force_range.cu` | Fuerza bruta con límites de rango    |

## Ejecución

```bash
cd gpu
make 04   # compila y ejecuta el hit #4
```

## Decisiones de diseño

- Un `.cu` por hit, autónomo, reutiliza kernels desde `include/`
- Makefile genera un binario por fuente objetivo
- CPU equivalente en `cpu/src/` para comparativa final
