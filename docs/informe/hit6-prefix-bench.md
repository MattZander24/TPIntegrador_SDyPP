# Hit #6 — Longitudes de prefijo en CUDA HASH

## Objetivo

Medir el tiempo de búsqueda de nonce para distintas longitudes de prefijo y
analizar la relación entre la longitud y el tiempo requerido.

## Configuración

- **GPU:** Tesla T4 (sm_75)
- **Threads:** 256 × 256 = 65536
- **Cadena base:** "hola"
- **Timeout por prueba:** 120 segundos

## Resultados

| Prefijo | Probabilidad | Nonce encontrado | Tiempo (s) | Nonces probados | Hashrate (H/s) |
|---------|-------------|-----------------|-----------|-----------------|---------------|
| "0"     | 1/16        | 94672           | 0.45      | 65536           | ~145K         |
| "00"    | 1/256       | 11869072        | 0.58      | 11.8M           | ~20M          |
| "000"   | 1/4096      | 1136814448      | 5.01      | 1.13B           | ~226M         |
| "0000"  | 1/65536     | 4126568848      | 80.48     | 4.12B           | ~51M          |

> **Nota:** el hashrate en "0" y "00" es impreciso por ser mediciones muy cortas.
> El valor estable se observa a partir de "000" (~226M H/s) y "0000" (~51M H/s).
> La variación se debe a que los primeros resultados dependen de cuán rápido
> cada hilo encuentra el nonce (distinto para cada corrida por el stepping).

## Análisis

### Relación tiempo vs. longitud de prefijo

```
n  | 16ⁿ       | Tiempo medido | Tiempo teórico (a 50M H/s)
---|-----------|---------------|---------------------------
1  | 16        | 0.45s         | < 1 ms
2  | 256       | 0.58s         | ~5 μs
3  | 4.096     | 5.01s         | ~80 μs
4  | 65.536    | 80.48s        | ~1.3 ms
5  | 1.048.576 | — (timeout)   | ~21 ms
```

La relación es **exponencial**: cada caracter hex adicional multiplica el
tiempo esperado por ~16.

### Prefijo más largo encontrado

**4 caracteres** ("0000") en **80.48 segundos**. Para 5+ caracteres se
necesitaría más paralelismo o reducir el espacio de búsqueda con rangos
(Hit #7).

### Observaciones

- El hashrate efectivo en T4 para MD5 con strings cortos es de
  aproximadamente **50–200 MHash/s**.
- Con 65536 threads concurrentes, la GPU está usando ~2560 CUDA cores
  (80 SMs × 32 cores cada uno), pero muchos threads están en espera por
  memory latency.
- La variabilidad entre corridas distintas se debe a que el nonce ganador
  se distribuye aleatoriamente.
