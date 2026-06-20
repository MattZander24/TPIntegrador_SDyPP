#!/usr/bin/env python3
"""Prueba de carga: envía N propuestas en paralelo, mide throughput.

Uso:
  python test_bulk.py --api-url http://localhost:8000 --sizes 1,10,100

Salida: CSV con size, total_time_s, throughput_proposals_s, blocks_sealed.
"""

import argparse
import concurrent.futures
import csv
import sys
import time
import uuid
from urllib.request import Request, urlopen
from urllib.error import URLError

API_URL = "http://localhost:8000"


def propose_law(api_url: str, text: str) -> dict | None:
    payload = f'{{"text":"{text}","author":"pk-test-{uuid.uuid4().hex[:8]}"}}'.encode()
    req = Request(
        f"{api_url}/api/laws",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=30) as resp:
            return {"status": resp.status, "body": resp.read().decode()}
    except URLError as e:
        return {"error": str(e)}


def get_chain_length(api_url: str) -> int:
    try:
        with urlopen(f"{api_url}/api/chain", timeout=10) as resp:
            import json
            data = json.loads(resp.read().decode())
            return len(data) if isinstance(data, list) else 0
    except URLError:
        return 0


def run_bulk_test(api_url: str, size: int) -> dict:
    print(f"  Enviando {size} propuestas...", end=" ", flush=True)
    start = time.monotonic()

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        texts = [f"Ley de prueba bulk #{i} ({uuid.uuid4().hex[:8]})" for i in range(size)]
        list(pool.map(lambda t: propose_law(api_url, t), texts))

    elapsed = time.monotonic() - start
    print(f"hecho en {elapsed:.2f}s")

    time.sleep(5)
    chain_len = get_chain_length(api_url)

    return {
        "size": size,
        "total_time_s": round(elapsed, 3),
        "throughput_proposals_s": round(size / elapsed, 2) if elapsed > 0 else 0,
        "blocks_sealed": chain_len,
    }


def main():
    parser = argparse.ArgumentParser(description="Bulk load test")
    parser.add_argument("--api-url", default=API_URL)
    parser.add_argument("--sizes", default="1,10,100,1000")
    parser.add_argument("--output", default="resultados_bulk.csv")
    args = parser.parse_args()

    sizes = [int(s.strip()) for s in args.sizes.split(",")]
    results = []

    for size in sizes:
        result = run_bulk_test(args.api_url, size)
        results.append(result)

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)

    print(f"\nResultados guardados en {args.output}")
    for r in results:
        print(f"  {r['size']:>5} props | {r['total_time_s']:>8.2f}s | "
              f"{r['throughput_proposals_s']:>8.2f} props/s | "
              f"{r['blocks_sealed']} bloques")


if __name__ == "__main__":
    main()
