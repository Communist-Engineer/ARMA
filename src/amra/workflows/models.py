"""Strict versioned payload models for Temporal boundaries."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field


class WorkflowPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class SatWorkflowInput(WorkflowPayload):
    schema_version: Literal["amra.sat-workflow.v1"] = "amra.sat-workflow.v1"
    obligation_id: str = Field(pattern=r"^[0-9a-f-]{36}$")
    cnf_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    idempotency_key: str = Field(min_length=1, max_length=255)
    worker_build_id: str = Field(min_length=1, max_length=255)


class ActivityCommand(WorkflowPayload):
    schema_version: Literal["amra.sat-activity.v1"] = "amra.sat-activity.v1"
    obligation_id: str
    cnf_digest: str
    idempotency_key: str
    worker_build_id: str
    prior_result_digest: str | None = None


class ActivityResult(WorkflowPayload):
    schema_version: Literal["amra.sat-activity-result.v1"] = "amra.sat-activity-result.v1"
    result_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    checkpoint: str


class WorkflowResult(WorkflowPayload):
    schema_version: Literal["amra.sat-workflow-result.v1"] = "amra.sat-workflow-result.v1"
    obligation_id: str
    manifest_digest: Annotated[str, Field(pattern=r"^sha256:[0-9a-f]{64}$")]
    state: Literal["SUCCEEDED", "FAILED", "CANCELLED", "HELD"]
    worker_build_id: str


class WorkflowMutation(WorkflowPayload):
    reason: str = Field(min_length=1, max_length=2000)
    actor: str = Field(min_length=1, max_length=255)
