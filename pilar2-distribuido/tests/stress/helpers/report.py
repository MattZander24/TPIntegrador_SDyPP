"""Genera reportes de resultados en terminal y en archivo JSON.

Evalúa cada métrica contra los SLOs definidos en config.py y produce
un dictamen PASS / FAIL claro con el detalle de cada check.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any


GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
BOLD   = "\033[1m"
RESET  = "\033[0m"


@dataclass
class Check:
    name: str
    value: Any
    threshold: Any
    passed: bool
    unit: str = ""

    def label(self) -> str:
        icon = f"{GREEN}PASS{RESET}" if self.passed else f"{RED}FAIL{RESET}"
        thresh = f"(umbral: {self.threshold}{self.unit})"
        return f"  [{icon}] {self.name}: {self.value}{self.unit} {thresh}"


class StressReport:
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.started_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.checks: list[Check] = []
        self.extra: dict[str, Any] = {}

    def add_check(self, name: str, value: Any, threshold: Any,
                  passed: bool, unit: str = "") -> None:
        self.checks.append(Check(name, value, threshold, passed, unit))

    def check_lte(self, name: str, value: float, threshold: float, unit: str = "") -> None:
        self.add_check(name, round(value, 2), threshold, value <= threshold, unit)

    def check_gte(self, name: str, value: float, threshold: float, unit: str = "") -> None:
        self.add_check(name, round(value, 2), threshold, value >= threshold, unit)

    def check_eq(self, name: str, value: Any, expected: Any, unit: str = "") -> None:
        self.add_check(name, value, expected, value == expected, unit)

    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    def print(self) -> None:
        verdict = f"{GREEN}{BOLD}PASSED{RESET}" if self.passed() else f"{RED}{BOLD}FAILED{RESET}"
        print(f"\n{'='*60}")
        print(f"{BOLD}Escenario:{RESET} {self.scenario}")
        print(f"{BOLD}Fecha:{RESET}     {self.started_at}")
        print(f"{BOLD}Veredicto:{RESET} {verdict}")
        print("-" * 60)
        for c in self.checks:
            print(c.label())
        if self.extra:
            print("-" * 60)
            print(f"{BOLD}Datos adicionales:{RESET}")
            for k, v in self.extra.items():
                print(f"  {k}: {v}")
        print("=" * 60)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "started_at": self.started_at,
            "passed": self.passed(),
            "checks": [
                {
                    "name": c.name,
                    "value": c.value,
                    "threshold": c.threshold,
                    "passed": c.passed,
                    "unit": c.unit,
                }
                for c in self.checks
            ],
            "extra": self.extra,
        }

    def save(self, directory: str = "stress-results") -> str:
        Path(directory).mkdir(parents=True, exist_ok=True)
        slug = self.scenario.lower().replace(" ", "_")
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = f"{directory}/{slug}_{ts}.json"
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
        print(f"\n{YELLOW}Reporte guardado en:{RESET} {path}")
        return path
