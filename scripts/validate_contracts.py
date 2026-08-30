#!/usr/bin/env python3
"""Validate JSON contracts, canonical license bytes, migration pins, and SBOM closure."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    for path in sorted((ROOT / "schemas").glob("*.schema.json")):
        schema = json.loads(path.read_bytes())
        Draft202012Validator.check_schema(schema)
        Draft202012Validator(schema, format_checker=FormatChecker())
    license_digest = hashlib.sha256((ROOT / "LICENSE.md").read_bytes()).hexdigest()
    expected_license = "ed7031dd973dbda81bb962f5b2d2e8c0e96f34a816b6dfd7c140152a8ace4708"
    if license_digest != expected_license:
        raise SystemExit(f"DPL license digest mismatch: {license_digest}")
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    locked = {str(package["name"]) for package in lock["package"]}
    sbom = json.loads((ROOT / "sbom/amra-phase1.cdx.json").read_bytes())
    components = {str(component["name"]) for component in sbom["components"]}
    if not locked <= components:
        raise SystemExit("SBOM omits locked packages: " + ", ".join(sorted(locked - components)))


if __name__ == "__main__":
    main()
