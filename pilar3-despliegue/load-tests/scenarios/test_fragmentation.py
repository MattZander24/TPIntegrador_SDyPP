#!/usr/bin/env python3
"""Prueba de fragmentación: varía FRAGMENT_SIZE, mide distribución.

Uso:
  python test_fragmentation.py --api-url http://localhost:8000 \
    --nonce-space 50000000 --fragments-pct 1,5,10,25,50

Salida: CSV con fragment_pct, fragment_size, tasks_created, time_to_seal_s.
"""

import argparse
import csv
import json
import time
import uuid
from urllib.request import Request, urlopen
from urllib.error import URLError

API_URL = "http://localhost:8000"
NONCE_SPACE = 50_000_000


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


def run_fragmentation_test(api_url: str, fragment_pct: int,
                           nonce_space: int) -> dict:
    fragment_size = int(nonce_space * fragment_pct / 100)
    tasks_count = nonce_space // max(fragment_size, 1)
    text = f"Test fragmentación {fragment_pct}% ({uuid.uuid4().hex[:8]})"

    print(f"  Fragmentación {fragment_pct}% (tamaño={fragment_size}, "
          f"tareas={tasks_count})...", end=" ", flush=True)

    start = time.monotonic()

    payload = json.dumps({
        "text": text,
        "author": f"pk-test-{uuid.uuid4().hex[:8]}",
        "fragment_size": fragment_size,
    }).encode()

    result = _req("POST", "/api/laws", payload)
    law_hash = result.get("body", {}).get("law_id", "")

    elapsed = time.monotonic() - start

    if law_hash:
        print(f"propuesta enviada en {elapsed:.2f}s")
    else:
        print(f"Fallo: {result}")

    return {
        "fragment_pct": fragment_pct,
        "fragment_size": fragment_size,
        "tasks_created": tasks_count,
        "proposal_time_s": round(elapsed, 3),
        "law_id": law_hash,
    }


def main():
    parser = argparse.ArgumentParser(description="Fragmentation test")
    parser.add_argument("--api-url", default=API_URL)
    parser.add_argument("--nonce-space", type=int, default=NONCE_SPACE)
    parser.add_argument("--fragments-pct", default="1,5,10,25,50")
    parser.add_argument("--output", default="resultados_fragmentacion.csv")
    args = parser.parse_args()

    percentages = [int(s.strip()) for s in args.fragments_pct.split(",")]
    results = []

    for pct in percentages:
        result = run_fragmentation_test(args.api_url, pct, args.nonce_space)
        results.append(result)

    with open(args.output, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=results[0].keys())
        w.writeheader()
        w.writerows(results)

    print(f"\nResultados guardados en {args.output}")
    for r in results:
        print(f"  {r['fragment_pct']:>3}% | size={r['fragment_size']:>8} | "
              f"tasks={r['tasks_created']:>5} | prop={r['proposal_time_s']:.2f}s")


if __name__ == "__main__":
    main()
