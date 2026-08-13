"""Strict Pydantic v2 models for every external control boundary."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

DigestText = Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
JsonUuid = Annotated[UUID, Field(strict=False)]


class StrictBoundaryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class ArtifactInitiateRequest(StrictBoundaryModel):
    digest: DigestText
    media_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)
    retention_class: str = Field(default="STANDARD", min_length=1, max_length=64)


class ArtifactInitiateResponse(StrictBoundaryModel):
    upload_id: UUID
    digest: DigestText
    object_version: int
    policy_version: str
    trace_id: UUID


class ArtifactFinalizeRequest(StrictBoundaryModel):
    upload_id: JsonUuid
    digest: DigestText
    content_base64: str
    created_actor: str = Field(min_length=1, max_length=255)


class ArtifactResponse(StrictBoundaryModel):
    digest: DigestText
    media_type: str
    size_bytes: int
    storage_uri: str
    retention_class: str
    object_version: int
    policy_version: str
    trace_id: UUID


class ObligationCreateRequest(StrictBoundaryModel):
    objective: str = Field(min_length=1, max_length=4000)
    cnf_digest: DigestText
    solver_budget: Decimal = Field(default=Decimal("25.000000"), ge=0)
    protected_verification_reserve: Decimal = Field(default=Decimal("2.000000"), ge=0)
    maximum_frontier_calls: int = Field(default=0, ge=0)


class MutationReason(StrictBoundaryModel):
    reason: str = Field(min_length=1, max_length=2000)
    actor: str = Field(min_length=1, max_length=255)


class ObligationResponse(StrictBoundaryModel):
    id: UUID
    objective: str
    cnf_digest: DigestText
    packet_digest: DigestText | None
    state: str
    object_version: int
    policy_version: str
    trace_id: UUID


class CostResponse(StrictBoundaryModel):
    events: list[dict[str, Any]]
    currency: Literal["USD"] = "USD"
    object_version: int
    policy_version: str
    trace_id: UUID


class HealthResponse(StrictBoundaryModel):
    status: Literal["ok", "unready"]
    checks: dict[str, bool]
