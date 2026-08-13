from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, text

from amra.adapters.postgres.health import validate_database_requirements

ROOT = Path(__file__).resolve().parents[1]


def test_dpl_exact_bytes_and_provenance_files() -> None:
    license_bytes = (ROOT / "LICENSE.md").read_bytes()
    assert hashlib.sha256(license_bytes).hexdigest() == (
        "ed7031dd973dbda81bb962f5b2d2e8c0e96f34a816b6dfd7c140152a8ace4708"
    )
    required = [
        "DPL_COMPLIANCE.md",
        "THIRD_PARTY_NOTICES.md",
        "docs/legal/LICENSE_PROVENANCE.md",
        "docs/legal/DEPENDENCY_LICENSE_POLICY.md",
        "docs/legal/DPL_DEPENDENCY_INTERPRETATION_REQUIRED.md",
        "docs/legal/dpl-registry-entry.yaml",
        "sbom/amra-phase1.cdx.json",
    ]
    assert all((ROOT / path).is_file() for path in required)


def test_migration_source_checksums() -> None:
    expected = {
        "001_initial.sql": "1b9c85bb73e9d4266020f3acb9f6cce5935b2a214d442edc9c8defd7130aed57",
        "002_phase1_trust_loop.sql": (
            "fba69b321e8d6fc17fb0aaebf99d9baeb1b2e641ac1befaacdedc14083430ca2"
        ),
    }
    for name, digest in expected.items():
        assert hashlib.sha256((ROOT / "db/migrations" / name).read_bytes()).hexdigest() == digest


@pytest.mark.integration
def test_fresh_postgresql_migration_when_database_is_available() -> None:
    database_url = os.environ.get("AMRA_TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("AMRA_TEST_DATABASE_URL is unset")
    configuration = Config(str(ROOT / "alembic.ini"))
    configuration.set_main_option(
        "script_location", str(ROOT / "src/amra/adapters/postgres/alembic")
    )
    configuration.set_main_option("sqlalchemy.url", database_url)
    command.upgrade(configuration, "head")
    engine = create_engine(database_url)
    with engine.connect() as connection:
        validate_database_requirements(connection)
        assert (
            connection.execute(text("SELECT count(*) FROM idempotency_records")).scalar_one() == 0
        )


def test_sbom_contains_locked_environment_and_proof_tools() -> None:
    sbom = json.loads((ROOT / "sbom/amra-phase1.cdx.json").read_bytes())
    names = {component["name"] for component in sbom["components"]}
    assert {"amra-cloud", "cadical", "drat-trim", "cake_lpr"} <= names
    locked_names = {
        package["name"]
        for package in json.loads((ROOT / "sbom/locked-python-components.json").read_bytes())
    }
    assert locked_names <= names
