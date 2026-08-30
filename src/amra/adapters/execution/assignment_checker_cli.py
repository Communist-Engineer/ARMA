"""Separate-process entry point for strict SAT assignment verification."""

from __future__ import annotations

import argparse
from pathlib import Path

from amra.adapters.artifacts.canonical import canonical_json_bytes
from amra.adapters.execution.dimacs import check_assignment
from amra.domain.errors import AmraError


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("cnf", type=Path)
    parser.add_argument("assignment", type=Path)
    parser.add_argument("report", type=Path)
    arguments = parser.parse_args()
    try:
        report = check_assignment(arguments.cnf.read_bytes(), arguments.assignment.read_bytes())
    except AmraError as error:
        report = {
            "accepted": False,
            "error": str(error),
            "schema_version": "amra.sat-assignment-check.v1",
        }
    arguments.report.write_bytes(canonical_json_bytes(report))
    return 0 if bool(report["accepted"]) else 2


if __name__ == "__main__":
    raise SystemExit(main())
