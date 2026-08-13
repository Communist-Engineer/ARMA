"""Add Phase 1 idempotency and missing-resource reason contracts."""

from __future__ import annotations

import hashlib
from pathlib import Path

from alembic import op

revision = "002_phase1_trust_loop"
down_revision = "001_checksum_baseline"
branch_labels = None
depends_on = None
LOCK_KEY = 0x414D5241001


def _source() -> bytes:
    root = Path(__file__).resolve().parents[6]
    content = (root / "db/migrations/002_phase1_trust_loop.sql").read_bytes()
    expected = "fba69b321e8d6fc17fb0aaebf99d9baeb1b2e641ac1befaacdedc14083430ca2"
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise RuntimeError(
            f"002_phase1_trust_loop.sql checksum mismatch: expected {expected}, got {actual}"
        )
    if not content.startswith(b"BEGIN;\n") or not content.endswith(b"\nCOMMIT;\n"):
        raise RuntimeError("002 migration transaction wrapper differs from its reviewed baseline")
    return content.removeprefix(b"BEGIN;\n").removesuffix(b"\nCOMMIT;\n")


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(f"SELECT pg_advisory_xact_lock({LOCK_KEY})")
    connection.exec_driver_sql(_source().decode("utf-8"), execution_options={"no_parameters": True})


def downgrade() -> None:
    raise RuntimeError(
        "AMRA ledger migrations use forward recovery; Phase 1 downgrade is undefined"
    )
