# Hit #4 — MD5 en GPU con CUDA

## Descripción

Programa que recibe un string por parámetro y calcula su hash MD5 utilizando la GPU (Tesla T4).

## Implementación

- **Kernel MD5:** `gpu/include/md5.cuh` — implementación completa del algoritmo MD5 como funciones `__device__`:
  - `md5_transform()`: función de compresión (64 pasos por bloque de 512 bits)
  - `md5_hash()`: padding + transformación iterativa + salida little-endian
- **Programa principal:** `gpu/src/03_md5_hash.cu` — asigna memoria GPU, lanza kernel de 1 thread, imprime resultado

## Ejecución

```bash
nvcc -arch=sm_75 -o md5_hash md5_hash.cu
./md5_hash "hola mundo"
```

## Resultados

| Entrada | MD5 (GPU) | MD5 (CPU/md5sum) | Coincide |
|---------|-----------|-------------------|----------|
| "hola mundo" | `0ad066a5d29f3f2a2a1c7c17dd082a79` | `0ad066a5d29f3f2a2a1c7c17dd082a79` | ✅ |

## Observaciones

- El kernel lanza 1 thread porque solo se necesita un hash. Esto no aprovecha el paralelismo de la GPU, pero sienta las bases para Hits #5–#7 donde se lanzarán miles de threads compitiendo por el nonce.
- Las constantes K[64] y S[64] se almacenan en memoria `__constant__` para acceso rápido desde todos los threads.
