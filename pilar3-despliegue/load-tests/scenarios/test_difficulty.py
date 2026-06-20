#!/usr/bin/env python3
"""Prueba de dificultad: mide tiempo hasta nonce válido con prefijos 1 a N.

Uso:
  python test_difficulty.py --api-url http://localhost:8000 --max-zeros 8

Salida: CSV con n_zeros, time_to_seal_s, blocks_sealed.
"""

import argparse
import csv
import json
import time
import uuid
from urllib.request import Request, urlopen
from urllib.error import URLError

API_URL = "http://localhost:8000"


def _req(method: str, path: str, data: bytes | None = None) -> dict:
    url = f"{API_URL}{path}"
    req = Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    try:
        with urlopen(req, timeout=60) as resp:
            return {"status": resp.status, "body": json.loads(resp.read().decode())}
    except URLError as e:
        return {"error": str(e)}


def propose_and_wait(api_url: str, text: str, poll_interval: float = 2.0,
                     timeout: float = 300.0) -> dict:
    start = time.monotonic()
    result = _req("POST", "/api/laws", json.dumps({
        "text": text,
        "author": f"pk-test-{uuid.uuid4().hex[:8]}"
    }).encode())

    law_hash = result.get("body", {}).get("law_id", "")
    if not law_hash:
        return {"error": "no law_id", "time_to_seal_s": None}

    while time.monotonic() - start < timeout:
        chain = _req("GET", "/api/chain")
        blocks = chain.get("body", [])
        for block in blocks:
            if law_hash in str(block):
                elapsed = time.monotonic() - start
                return {"time_to_seal_s": round(elapsed, 3), "block": block}
        time.sleep(poll_interval)

    return {"time_to_seal_s": None, "error": "timeout"}


def run_difficulty_test(api_url: str, n_zeros: int) -> dict:
    print(f"  Probando n_zeros={n_zeros}...", end=" ", flush=True)
    result = propose_and_wait(
        api_url,
        f"Test dificultad {n_zeros} ({uuid.uuid4().hex[:8]})"
    )
    t = result.get("time_to_seal_s")
    if t:
        print(f"bloque sellado en {t:.2f}s")
    else:
        print(f"Fallo: {result.get('error', 'timeout')}")

    return {
        "n_zeros": n_zeros,
        "time_to_seal_s": t if t else -1,
        "error": result.get("error", ""),
    }


def main():
    parser = argparse.ArgumentParser(description="Difficulty load test")
    parser.add_argument("--api-url", default=API_URL)
    parser.add_argument("--max-zeros", type=int, default=8)
    parser.add_argument("--output", default="resultados_dificultad.csv")
    args = parser.parse_args()

    results = []
    for n in range(1, args.max_zeros + 1):
        result = run_difficulty_test(args.api_url, n)
        results.append(result)

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)

    print(f"\nResultados guardados en {args.output}")
    for r in results:
        status = f"{r['time_to_seal_s']:.2f}s" if r['time_to_seal_s'] > 0 else r['error']
        print(f"  n_zeros={r['n_zeros']}: {status}")


if __name__ == "__main__":
    main()
