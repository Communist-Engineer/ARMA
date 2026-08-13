"""Minimum Phase 1 FastAPI control surface."""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, Header, HTTPException, status

from amra.adapters.artifacts.canonical import canonical_json_bytes
from amra.adapters.costs.memory import BudgetPolicy, InMemoryCostLedger
from amra.adapters.execution.dimacs import parse_dimacs
from amra.adapters.ledger.memory import InMemoryLedger
from amra.api.models import (
    ArtifactFinalizeRequest,
    ArtifactInitiateRequest,
    ArtifactInitiateResponse,
    ArtifactResponse,
    CostResponse,
    HealthResponse,
    MutationReason,
    ObligationCreateRequest,
    ObligationResponse,
)
from amra.domain.budget import Money
from amra.domain.errors import AmraError
from amra.domain.identifiers import ObligationId, Sha256Digest
from amra.domain.obligation import Obligation, ObligationState
from amra.ports.artifacts import ArtifactPort

POLICY_VERSION = "0.1.0"


@dataclass(slots=True)
class PendingUpload:
    upload_id: UUID
    request: ArtifactInitiateRequest


@dataclass(slots=True)
class ApiObligation:
    obligation: Obligation
    cnf_digest: Sha256Digest
    solver_budget: Money
    verification_reserve: Money
    maximum_frontier_calls: int


@dataclass(slots=True)
class ApiState:
    artifacts: ArtifactPort
    ledger: InMemoryLedger
    costs: InMemoryCostLedger
    pending: dict[UUID, PendingUpload]
    obligations: dict[str, ApiObligation]
    mutations: dict[str, object]
    tool_paths: tuple[Path, ...]


def _trace() -> UUID:
    return uuid4()


def _require_key(key: str | None) -> str:
    if key is None or not key.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Idempotency-Key is required")
    return key


def create_app(artifacts: ArtifactPort, *, tool_paths: tuple[Path, ...] = ()) -> FastAPI:
    state = ApiState(
        artifacts=artifacts,
        ledger=InMemoryLedger(),
        costs=InMemoryCostLedger(
            BudgetPolicy(
                category_limits={
                    "solver": Money.usd("25"),
                    "verification": Money.usd("0"),
                },
                protected_verification_reserve=Money.usd("2"),
            )
        ),
        pending={},
        obligations={},
        mutations={},
        tool_paths=tool_paths,
    )
    app = FastAPI(
        title="AMRA Cloud Control API",
        version="0.1.0",
        description="Control boundary for DPL-licensed commons software",
    )
    app.state.amra = state

    @app.post("/v1/artifacts:initiate", response_model=ArtifactInitiateResponse)
    def initiate_artifact(
        request: ArtifactInitiateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ArtifactInitiateResponse:
        key = _require_key(idempotency_key)
        existing = state.mutations.get(key)
        if isinstance(existing, ArtifactInitiateResponse):
            return existing
        upload = PendingUpload(uuid4(), request)
        state.pending[upload.upload_id] = upload
        response = ArtifactInitiateResponse(
            upload_id=upload.upload_id,
            digest=request.digest,
            object_version=0,
            policy_version=POLICY_VERSION,
            trace_id=_trace(),
        )
        state.mutations[key] = response
        return response

    @app.post("/v1/artifacts:finalize", response_model=ArtifactResponse)
    def finalize_artifact(
        request: ArtifactFinalizeRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ArtifactResponse:
        key = _require_key(idempotency_key)
        existing = state.mutations.get(key)
        if isinstance(existing, ArtifactResponse):
            return existing
        pending = state.pending.get(request.upload_id)
        if pending is None or pending.request.digest != request.digest:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "upload initiation does not match finalize"
            )
        try:
            content = base64.b64decode(request.content_base64, validate=True)
            metadata = state.artifacts.put_if_absent(
                content,
                media_type=pending.request.media_type,
                actor=request.created_actor,
                retention_class=pending.request.retention_class,
                expected_digest=Sha256Digest(request.digest),
            )
        except (binascii.Error, AmraError) as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
        response = ArtifactResponse(
            digest=str(metadata.digest),
            media_type=metadata.media_type,
            size_bytes=metadata.size_bytes,
            storage_uri=metadata.storage_uri,
            retention_class=metadata.retention_class,
            object_version=0,
            policy_version=POLICY_VERSION,
            trace_id=_trace(),
        )
        state.mutations[key] = response
        return response

    @app.post("/v1/obligations", response_model=ObligationResponse)
    def create_obligation(
        request: ObligationCreateRequest,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ObligationResponse:
        key = _require_key(idempotency_key)
        existing = state.mutations.get(key)
        if isinstance(existing, ObligationResponse):
            return existing
        try:
            state.artifacts.verify(Sha256Digest(request.cnf_digest))
            obligation = Obligation(
                ObligationId.new(),
                request.objective,
                updated_at=datetime.now(UTC),
            )
            obligation = state.ledger.create_obligation(obligation, key)
        except (AmraError, FileNotFoundError) as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
        state.obligations[str(obligation.id)] = ApiObligation(
            obligation,
            Sha256Digest(request.cnf_digest),
            Money.usd(request.solver_budget),
            Money.usd(request.protected_verification_reserve),
            request.maximum_frontier_calls,
        )
        response = _obligation_response(state.obligations[str(obligation.id)])
        state.mutations[key] = response
        return response

    def mutate(
        obligation_id: UUID,
        target: ObligationState,
        key: str | None,
    ) -> ObligationResponse:
        idempotency_key = _require_key(key)
        existing = state.mutations.get(idempotency_key)
        if isinstance(existing, ObligationResponse):
            return existing
        record = state.obligations.get(str(obligation_id))
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "obligation is unknown")
        try:
            current = record.obligation
            transitioned = current.transition(
                target,
                expected_version=current.version,
                at=datetime.now(UTC),
            )
            record.obligation = state.ledger.compare_and_set_obligation(
                transitioned,
                current.version,
                idempotency_key,
            )
        except AmraError as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        response = _obligation_response(record)
        state.mutations[idempotency_key] = response
        return response

    @app.post("/v1/obligations/{obligation_id}:freeze", response_model=ObligationResponse)
    def freeze_obligation(
        obligation_id: UUID,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ObligationResponse:
        key = _require_key(idempotency_key)
        existing = state.mutations.get(key)
        if isinstance(existing, ObligationResponse):
            return existing
        record = state.obligations.get(str(obligation_id))
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "obligation is unknown")
        try:
            parse_dimacs(state.artifacts.read(record.cnf_digest))
            packet = state.artifacts.put_if_absent(
                canonical_json_bytes(
                    {
                        "budgets": {
                            "maximum_frontier_calls": record.maximum_frontier_calls,
                            "protected_verification": str(record.verification_reserve.amount),
                            "solver": str(record.solver_budget.amount),
                        },
                        "cnf_digest": str(record.cnf_digest),
                        "objective": record.obligation.objective,
                        "schema_version": "amra.phase1-api-obligation.v1",
                    }
                ),
                media_type="application/vnd.amra.obligation+json",
                actor="amra:api",
                retention_class="LEDGER",
            )
            current = record.obligation
            ready = current.with_packet(packet.digest).transition(
                ObligationState.READY,
                expected_version=current.version,
                at=datetime.now(UTC),
            )
            record.obligation = state.ledger.compare_and_set_obligation(
                ready,
                current.version,
                f"{key}:ready",
            )
            state.costs.reserve("solver", record.solver_budget, f"{key}:reserve")
            current = record.obligation
            reserved = current.transition(
                ObligationState.RESERVED,
                expected_version=current.version,
                at=datetime.now(UTC),
            )
            record.obligation = state.ledger.compare_and_set_obligation(
                reserved,
                current.version,
                f"{key}:reserved",
            )
        except (AmraError, FileNotFoundError) as error:
            raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error
        response = _obligation_response(record)
        state.mutations[key] = response
        return response

    @app.post("/v1/obligations/{obligation_id}:start", response_model=ObligationResponse)
    def start_obligation(
        obligation_id: UUID,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ObligationResponse:
        return mutate(obligation_id, ObligationState.RUNNING, idempotency_key)

    @app.post("/v1/obligations/{obligation_id}:cancel", response_model=ObligationResponse)
    def cancel_obligation(
        obligation_id: UUID,
        _: MutationReason,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ObligationResponse:
        return mutate(obligation_id, ObligationState.CANCELLED, idempotency_key)

    @app.post("/v1/obligations/{obligation_id}:hold", response_model=ObligationResponse)
    def hold_obligation(
        obligation_id: UUID,
        _: MutationReason,
        idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    ) -> ObligationResponse:
        return mutate(obligation_id, ObligationState.HELD, idempotency_key)

    @app.get("/v1/obligations/{obligation_id}", response_model=ObligationResponse)
    def get_obligation(obligation_id: UUID) -> ObligationResponse:
        record = state.obligations.get(str(obligation_id))
        if record is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "obligation is unknown")
        return _obligation_response(record)

    @app.get("/v1/costs", response_model=CostResponse)
    def get_costs() -> CostResponse:
        events = [
            {
                "amount": str(event.amount.amount),
                "category": event.category,
                "currency": event.amount.currency,
                "idempotency_key": event.idempotency_key,
                "state": event.state.value,
            }
            for event in state.costs.events()
        ]
        return CostResponse(
            events=events,
            object_version=len(events),
            policy_version=POLICY_VERSION,
            trace_id=_trace(),
        )

    @app.get("/health/live", response_model=HealthResponse)
    def live() -> HealthResponse:
        return HealthResponse(status="ok", checks={"process": True})

    @app.get("/health/ready", response_model=HealthResponse)
    def ready() -> HealthResponse:
        checks = {
            "artifact_store": True,
            "proof_tools": all(path.is_file() for path in state.tool_paths),
        }
        return HealthResponse(status="ok" if all(checks.values()) else "unready", checks=checks)

    return app


def _obligation_response(record: ApiObligation) -> ObligationResponse:
    obligation = record.obligation
    return ObligationResponse(
        id=obligation.id.value,
        objective=obligation.objective,
        cnf_digest=str(record.cnf_digest),
        packet_digest=None if obligation.packet_digest is None else str(obligation.packet_digest),
        state=obligation.state.value,
        object_version=obligation.version,
        policy_version=obligation.policy_version,
        trace_id=_trace(),
    )
