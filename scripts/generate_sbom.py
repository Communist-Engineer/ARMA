#!/usr/bin/env python3
"""Generate a reproducible CycloneDX inventory from uv.lock and proof-tool pins."""

from __future__ import annotations

import hashlib
import json
import tomllib
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]


def component_for_package(package: dict[str, object]) -> dict[str, object]:
    name = str(package["name"])
    version = str(package["version"])
    normalized = name.replace("_", "-")
    return {
        "bom-ref": f"pkg:pypi/{quote(normalized)}@{quote(version)}",
        "name": name,
        "purl": f"pkg:pypi/{quote(normalized)}@{quote(version)}",
        "type": "library" if name != "amra-cloud" else "application",
        "version": version,
    }


def main() -> None:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    python_components = [component_for_package(package) for package in lock["package"]]
    tool_lock = json.loads((ROOT / "config/toolchain.lock.json").read_bytes())
    licenses = {"cadical": "MIT", "drat-trim": "MIT", "cake_lpr": "BSD-2-Clause"}
    tools: list[dict[str, object]] = []
    for tool in tool_lock["tools"]:
        name = tool["name"]
        repository_path = tool["source_repository"].split("github.com/")[1]
        bom_reference = f"pkg:github/{repository_path}@{tool['source_commit']}"
        component: dict[str, object] = {
            "bom-ref": bom_reference,
            "externalReferences": [
                {"type": "vcs", "url": f"{tool['source_repository']}@{tool['source_commit']}"}
            ],
            "licenses": [{"license": {"id": licenses[name]}}],
            "name": name,
            "properties": [
                {"name": "amra:source-commit", "value": tool["source_commit"]},
                {"name": "amra:image-digest", "value": str(tool["image_digest"])},
                {
                    "name": "amra:local-executable-sha256",
                    "value": tool["local_executable_sha256"],
                },
                {"name": "amra:compiler", "value": tool["compiler"]},
                {"name": "amra:execution-boundary", "value": "separate-process"},
            ],
            "type": "application",
            "version": tool["version"],
        }
        # The canonical SBOM is generated from the reviewed lock, not from whatever
        # compiler happens to be installed on the current host. Per-build executable
        # and image identities are retained separately as build evidence.
        component["hashes"] = [{"alg": "SHA-256", "content": tool["local_executable_sha256"]}]
        tools.append(component)
    components = sorted(python_components + tools, key=lambda item: str(item["bom-ref"]))
    root_ref = next(
        str(component["bom-ref"]) for component in components if component["name"] == "amra-cloud"
    )
    bom = {
        "bomFormat": "CycloneDX",
        "components": components,
        "dependencies": [
            {
                "ref": root_ref,
                "dependsOn": [
                    component["bom-ref"]
                    for component in components
                    if component["bom-ref"] != root_ref
                ],
            }
        ],
        "metadata": {
            "component": {
                "bom-ref": root_ref,
                "licenses": [{"license": {"name": "Dialectical Public License v1.0"}}],
                "name": "amra-cloud",
                "type": "application",
                "version": "0.1.0",
            },
            "properties": [
                {
                    "name": "amra:lock-digest",
                    "value": hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
                },
                {"name": "amra:resolution-date", "value": "2026-08-12"},
            ],
            "timestamp": "2026-08-12T00:00:00Z",
            "tools": {
                "components": [
                    {"name": "scripts/generate_sbom.py", "type": "application", "version": "1"}
                ]
            },
        },
        "serialNumber": "urn:uuid:7fba2c7e-d20c-5aa6-b7b0-43b08af5ed60",
        "specVersion": "1.6",
        "version": 1,
    }
    output = ROOT / "sbom"
    output.mkdir(parents=True, exist_ok=True)
    (output / "amra-phase1.cdx.json").write_text(json.dumps(bom, indent=2, sort_keys=True) + "\n")
    (output / "locked-python-components.json").write_text(
        json.dumps(
            [
                {"name": package["name"], "version": package["version"]}
                for package in sorted(lock["package"], key=lambda item: str(item["name"]))
            ],
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )


if __name__ == "__main__":
    main()
