"""Replay-safe Temporal orchestration for the Phase 1 SAT trust loop."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from amra.workflows.models import (
        ActivityCommand,
        ActivityResult,
        SatWorkflowInput,
        WorkflowMutation,
        WorkflowResult,
    )

_RETRY_POLICY = RetryPolicy(
    initial_interval=timedelta(seconds=1),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=5,
    non_retryable_error_types=[
        "InvalidCertificate",
        "InvalidAssignment",
        "InvalidDimacs",
        "BudgetExhausted",
        "ProceduralHold",
        "OperatorCancellation",
    ],
)


@workflow.defn(name="SatVerificationWorkflow")
class SatVerificationWorkflow:
    """One logical result and debit survive activity and worker retries."""

    def __init__(self) -> None:
        self._state = "DRAFT"
        self._held = False
        self._cancelled = False
        self._checkpoint: str | None = None

    @workflow.run
    async def run(self, raw_input: dict[str, Any]) -> dict[str, Any]:
        payload = SatWorkflowInput.model_validate(raw_input)
        workflow.patched("amra-phase1-sat-workflow-v1")
        try:
            frozen = await self._activity("freeze_and_reserve", payload, None, "RESERVED")
            solved = await self._activity("solve_cnf", payload, frozen.result_digest, "RUNNING")
            checked = await self._activity(
                "verify_and_record_evidence",
                payload,
                solved.result_digest,
                "AWAITING_EVIDENCE",
            )
            finalized = await self._activity(
                "finalize_execution_manifest",
                payload,
                checked.result_digest,
                "FINALIZING",
            )
            reconciled = await self._activity(
                "reconcile_cost",
                payload,
                finalized.result_digest,
                "RECONCILING",
            )
            self._state = "SUCCEEDED"
            return WorkflowResult(
                obligation_id=payload.obligation_id,
                manifest_digest=reconciled.result_digest,
                state="SUCCEEDED",
                worker_build_id=payload.worker_build_id,
            ).model_dump(mode="json")
        except ApplicationError:
            self._state = "CANCELLED" if self._cancelled else "FAILED"
            raise

    async def _activity(
        self,
        name: str,
        payload: SatWorkflowInput,
        prior: str | None,
        state: str,
    ) -> ActivityResult:
        await self._gate()
        self._state = state
        command = ActivityCommand(
            obligation_id=payload.obligation_id,
            cnf_digest=payload.cnf_digest,
            idempotency_key=f"{payload.idempotency_key}:{name}",
            worker_build_id=payload.worker_build_id,
            prior_result_digest=prior,
        )
        result = await workflow.execute_activity(
            name,
            command.model_dump(mode="json"),
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=30),
            retry_policy=_RETRY_POLICY,
            cancellation_type=workflow.ActivityCancellationType.WAIT_CANCELLATION_COMPLETED,
        )
        validated = ActivityResult.model_validate(result)
        self._checkpoint = validated.checkpoint
        return validated

    async def _gate(self) -> None:
        if self._cancelled:
            raise ApplicationError(
                "operator cancelled workflow", type="OperatorCancellation", non_retryable=True
            )
        if self._held:
            self._state = "HELD"
            await workflow.wait_condition(lambda: not self._held or self._cancelled)
        if self._cancelled:
            raise ApplicationError(
                "operator cancelled workflow", type="OperatorCancellation", non_retryable=True
            )

    @workflow.signal
    async def hold(self, raw: dict[str, Any]) -> None:
        WorkflowMutation.model_validate(raw)
        self._held = True

    @workflow.signal
    async def resume(self, raw: dict[str, Any]) -> None:
        WorkflowMutation.model_validate(raw)
        self._held = False

    @workflow.signal
    async def cancel(self, raw: dict[str, Any]) -> None:
        WorkflowMutation.model_validate(raw)
        self._cancelled = True

    @workflow.query
    def status(self) -> dict[str, Any]:
        return {
            "cancelled": self._cancelled,
            "checkpoint": self._checkpoint,
            "held": self._held,
            "state": self._state,
        }
