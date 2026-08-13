"""PostgreSQL extension and version readiness checks."""

from __future__ import annotations

from sqlalchemy import Connection, text

from amra.domain.errors import InvariantViolation


def validate_database_requirements(connection: Connection) -> None:
    server_version = int(connection.execute(text("SHOW server_version_num")).scalar_one())
    if server_version < 180000 or server_version >= 190000:
        raise InvariantViolation("AMRA Phase 1 requires PostgreSQL major version 18")
    rows = connection.execute(
        text("SELECT extname, extversion FROM pg_extension WHERE extname IN ('pgcrypto', 'vector')")
    ).all()
    installed = {str(name): str(version) for name, version in rows}
    missing = {"pgcrypto", "vector"} - installed.keys()
    if missing:
        raise InvariantViolation(
            "required PostgreSQL extensions are absent: " + ", ".join(sorted(missing))
        )
    vector_version = tuple(int(part) for part in installed["vector"].split("."))
    if vector_version < (0, 8, 6):
        raise InvariantViolation("AMRA Phase 1 requires pgvector 0.8.6 or a reviewed patch")
