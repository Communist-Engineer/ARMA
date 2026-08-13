"""Apply the reviewed initial ledger schema after exact-byte verification."""

from __future__ import annotations

import hashlib
from pathlib import Path

from alembic import op

revision = "001_checksum_baseline"
down_revision = None
branch_labels = None
depends_on = None

EXPECTED_SHA256 = "1b9c85bb73e9d4266020f3acb9f6cce5935b2a214d442edc9c8defd7130aed57"
LOCK_KEY = 0x414D5241001


def _source() -> bytes:
    root = Path(__file__).resolve().parents[6]
    content = (root / "db/migrations/001_initial.sql").read_bytes()
    actual = hashlib.sha256(content).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(
            f"001_initial.sql checksum mismatch: expected {EXPECTED_SHA256}, got {actual}"
        )
    if not content.startswith(b"BEGIN;\n") or not content.endswith(b"\nCOMMIT;\n"):
        raise RuntimeError("001_initial.sql transaction wrapper differs from the reviewed baseline")
    return content.removeprefix(b"BEGIN;\n").removesuffix(b"\nCOMMIT;\n")


def upgrade() -> None:
    connection = op.get_bind()
    connection.exec_driver_sql(f"SELECT pg_advisory_xact_lock({LOCK_KEY})")
    connection.exec_driver_sql(_source().decode("utf-8"))


def downgrade() -> None:
    raise RuntimeError(
        "AMRA ledger migrations use forward recovery; baseline downgrade is undefined"
    )
