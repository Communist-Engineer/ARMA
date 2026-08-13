"""SQLAlchemy 2 Core obligation transaction adapter."""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import UTC
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from amra.domain.errors import DuplicateIdempotencyConflict, InvalidTransition
from amra.domain.identifiers import ObligationId, Sha256Digest
from amra.domain.obligation import Obligation, ObligationState


class PostgresLedger:
    """Perform explicit transactions and compare-and-set updates without ORM state."""

    def __init__(self, engine: Engine, program_id: UUID) -> None:
        self._engine = engine
        self._program_id = program_id

    def _operation(self, connection: Any, key: str, signature: Mapping[str, object]) -> bool:
        inserted = connection.execute(
            text(
                "INSERT INTO idempotency_records (idempotency_key, operation_digest, response) "
                "VALUES (:key, encode(digest(:signature, 'sha256'), 'hex'), '{}'::jsonb) "
                "ON CONFLICT (idempotency_key) DO NOTHING RETURNING idempotency_key"
            ),
            {"key": key, "signature": json.dumps(signature, sort_keys=True, separators=(",", ":"))},
        ).scalar_one_or_none()
        if inserted is not None:
            return False
        existing = connection.execute(
            text("SELECT operation_digest FROM idempotency_records WHERE idempotency_key=:key"),
            {"key": key},
        ).scalar_one()
        expected = connection.execute(
            text("SELECT encode(digest(:signature, 'sha256'), 'hex')"),
            {"signature": json.dumps(signature, sort_keys=True, separators=(",", ":"))},
        ).scalar_one()
        if existing != expected:
            raise DuplicateIdempotencyConflict(f"ledger key {key!r} has conflicting semantics")
        return True

    def create_obligation(self, obligation: Obligation, idempotency_key: str) -> Obligation:
        signature = {
            "action": "create",
            "id": str(obligation.id),
            "objective": obligation.objective,
        }
        with self._engine.begin() as connection:
            duplicate = self._operation(connection, idempotency_key, signature)
            if not duplicate:
                connection.execute(
                    text(
                        "INSERT INTO obligations "
                        "(id, program_id, objective, state, state_version, "
                        "policy_versions, updated_at) "
                        "VALUES (:id, :program, :objective, :state, :version, "
                        "CAST(:policy AS jsonb), :updated)"
                    ),
                    {
                        "id": obligation.id.value,
                        "program": self._program_id,
                        "objective": obligation.objective,
                        "state": obligation.state.value,
                        "version": obligation.version,
                        "policy": json.dumps({"phase1": obligation.policy_version}),
                        "updated": obligation.updated_at,
                    },
                )
        return self.get_obligation(str(obligation.id))

    def get_obligation(self, obligation_id: str) -> Obligation:
        with self._engine.connect() as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT id, objective, state::text, state_version, packet_artifact_digest, "
                        "policy_versions, updated_at FROM obligations WHERE id=:id"
                    ),
                    {"id": UUID(obligation_id)},
                )
                .mappings()
                .one()
            )
        policies: dict[str, object] = row["policy_versions"]
        packet = row["packet_artifact_digest"]
        return Obligation(
            ObligationId(row["id"]),
            str(row["objective"]),
            ObligationState(str(row["state"])),
            int(row["state_version"]),
            None if packet is None else Sha256Digest(str(packet)),
            str(policies.get("phase1", "0.1.0")),
            row["updated_at"].astimezone(UTC),
        )

    def compare_and_set_obligation(
        self,
        obligation: Obligation,
        expected_version: int,
        idempotency_key: str,
    ) -> Obligation:
        signature = {
            "action": "cas",
            "id": str(obligation.id),
            "expected": expected_version,
            "target": obligation.state.value,
            "version": obligation.version,
        }
        with self._engine.begin() as connection:
            duplicate = self._operation(connection, idempotency_key, signature)
            if not duplicate:
                updated = connection.execute(
                    text(
                        "UPDATE obligations SET state=:state, state_version=:new_version, "
                        "packet_artifact_digest=:packet, updated_at=:updated "
                        "WHERE id=:id AND state_version=:expected"
                    ),
                    {
                        "state": obligation.state.value,
                        "new_version": obligation.version,
                        "packet": None
                        if obligation.packet_digest is None
                        else str(obligation.packet_digest),
                        "updated": obligation.updated_at,
                        "id": obligation.id.value,
                        "expected": expected_version,
                    },
                )
                if updated.rowcount != 1:
                    raise InvalidTransition(
                        "PostgreSQL compare-and-set rejected a stale object version"
                    )
        return self.get_obligation(str(obligation.id))
