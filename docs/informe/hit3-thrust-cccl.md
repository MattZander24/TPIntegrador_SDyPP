# Hit #3 — Librerías CUDA (Thrust / CCCL)

## CCCL (CUDA Core Compute Libraries)

Repositorio que unifica **Thrust**, **CUB** y **libcudacxx** en un solo proyecto.

- **Último release:** v3.3.3 (20/04/2026)
- **Repo:** https://github.com/NVIDIA/cccl
- **Documentación:** https://nvidia.github.io/cccl

### ¿Qué incluye?

| Librería | Rol |
|----------|-----|
| **Thrust** | Algoritmos paralelos estilo STL (sort, reduce, transform) |
| **CUB** | Primitivas de bajo nivel para kernels CUDA |
| **libcudacxx** | Standard Library de C++ para host y device |

### Thrust

El repositorio original `github.com/nvidia/thrust` fue archivado en marzo de 2024. Ahora Thrust forma parte de CCCL y se incluye con el CUDA Toolkit. No requiere instalación adicional.

## Diferencia: CUDA "a pelo" vs Thrust

| Aspecto | CUDA directo | Thrust |
|---------|-------------|--------|
| Gestión de memoria | `cudaMalloc` / `cudaMemcpy` / `cudaFree` | `thrust::device_vector<T>` (automática) |
| Lanzar kernel | `kernel<<<grid, block>>>` | Algoritmos tipo `thrust::sort`, `thrust::reduce` |
| Iteradores | manual (índices) | `begin()` / `end()` estilo STL |
| Curva de aprendizaje | alta (arquitectura GPU, shared mem, etc.) | baja (similar a `std::vector` + `<algorithm>`) |
| Control fino | total (shared mem, warp, coalescing) | abstraído (el backend elige) |
| Portabilidad | solo GPU NVIDIA | GPU + CPU (TBB/OpenMP backends) |

## Ejemplo ejecutado

Programa: `02_thrust_vector.cu`
- Crea `host_vector<int>` con valores 10, 20, 30, 40
- Copia a `device_vector`
- Copia de vuelta a host e imprime

**Salida:**
```
Thrust device_vector contents:
  result[0] = 10
  result[1] = 20
  result[2] = 30
  result[3] = 40
```
