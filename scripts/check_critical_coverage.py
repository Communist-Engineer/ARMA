"""Require complete branch coverage for Phase 1 trust primitives."""

from __future__ import annotations

import json
from pathlib import Path

CRITICAL = (
    "src/amra/domain/identifiers.py",
    "src/amra/domain/budget.py",
    "src/amra/domain/obligation.py",
    "src/amra/adapters/execution/dimacs.py",
    "src/amra/adapters/costs/memory.py",
    "src/amra/adapters/ledger/memory.py",
)


def main() -> int:
    report = json.loads(Path("build/coverage.json").read_bytes())
    failures: list[str] = []
    for path in CRITICAL:
        summary = report["files"][path]["summary"]
        if summary["percent_covered"] != 100.0:
            failures.append(f"{path}: {summary['percent_covered']:.2f}%")
    if failures:
        raise SystemExit("critical branch coverage below 100%: " + ", ".join(failures))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
