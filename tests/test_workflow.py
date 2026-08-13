from __future__ import annotations

import asyncio
import hashlib
from collections import Counter
from typing import Any
from uuid import uuid4

import pytest
from temporalio import activity
from temporalio.client import WorkflowFailureError
from temporalio.exceptions import ApplicationError
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Replayer, Worker

from amra.workflows.models import SatWorkflowInput
from amra.workflows.sat_verification import SatVerificationWorkflow


def digest(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def payload() -> dict[str, Any]:
    return SatWorkflowInput(
        obligation_id=str(uuid4()),
        cnf_digest=digest("cnf"),
        idempotency_key="workflow-test",
        worker_build_id="amra-phase1-v1",
    ).model_dump(mode="json")


@pytest.mark.asyncio
async def test_time_skipping_workflow_executes_one_logical_cost_debit() -> None:
    calls: Counter[str] = Counter()

    def handler(name: str):  # type: ignore[no-untyped-def]
        @activity.defn(name=name)
        async def run(raw: dict[str, Any]) -> dict[str, Any]:
            calls[name] += 1
            return {
                "schema_version": "amra.sat-activity-result.v1",
                "result_digest": digest(name),
                "checkpoint": name,
            }

        return run

    activities = [
        handler(name)
        for name in (
            "freeze_and_reserve",
            "solve_cnf",
            "verify_and_record_evidence",
            "finalize_execution_manifest",
            "reconcile_cost",
        )
    ]
    async with (
        await WorkflowEnvironment.start_time_skipping() as environment,
        Worker(
            environment.client,
            task_queue="amra-time-skip",
            workflows=[SatVerificationWorkflow],
            activities=activities,
        ),
    ):
        handle = await environment.client.start_workflow(
            SatVerificationWorkflow.run,
            payload(),
            id="time-skip",
            task_queue="amra-time-skip",
        )
        result = await handle.result()
        history = await handle.fetch_history()
        replay = await Replayer(
            workflows=[SatVerificationWorkflow],
            build_id="amra-phase1-v1",
        ).replay_workflow(history)
        assert replay.replay_failure is None
    assert result["state"] == "SUCCEEDED"
    assert calls["reconcile_cost"] == 1
    assert all(count == 1 for count in calls.values())


@pytest.mark.asyncio
async def test_solver_side_effect_recovers_idempotently_after_worker_like_interruption() -> None:
    attempts = 0
    durable_result: dict[str, str] = {}

    def ordinary(name: str):  # type: ignore[no-untyped-def]
        @activity.defn(name=name)
        async def run(raw: dict[str, Any]) -> dict[str, Any]:
            return {
                "schema_version": "amra.sat-activity-result.v1",
                "result_digest": digest(name),
                "checkpoint": name,
            }

        return run

    @activity.defn(name="solve_cnf")
    async def interrupted_solver(raw: dict[str, Any]) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        key = str(raw["idempotency_key"])
        if key not in durable_result:
            durable_result[key] = digest("solver-output")
            raise ApplicationError(
                "worker lost after durable solver output", type="SpotInterruption"
            )
        return {
            "schema_version": "amra.sat-activity-result.v1",
            "result_digest": durable_result[key],
            "checkpoint": "solver-output-reused",
        }

    activities = [
        ordinary("freeze_and_reserve"),
        interrupted_solver,
        ordinary("verify_and_record_evidence"),
        ordinary("finalize_execution_manifest"),
        ordinary("reconcile_cost"),
    ]
    async with (
        await WorkflowEnvironment.start_time_skipping() as environment,
        Worker(
            environment.client,
            task_queue="amra-recovery",
            workflows=[SatVerificationWorkflow],
            activities=activities,
        ),
    ):
        result = await environment.client.execute_workflow(
            SatVerificationWorkflow.run,
            payload(),
            id="worker-recovery",
            task_queue="amra-recovery",
        )
    assert result["state"] == "SUCCEEDED"
    assert attempts == 2
    assert len(durable_result) == 1


@pytest.mark.asyncio
async def test_workflow_cancellation_signal_is_typed() -> None:
    gate = asyncio.Event()

    @activity.defn(name="freeze_and_reserve")
    async def freeze(raw: dict[str, Any]) -> dict[str, Any]:
        gate.set()
        return {
            "schema_version": "amra.sat-activity-result.v1",
            "result_digest": digest("freeze"),
            "checkpoint": "freeze",
        }

    def ordinary(name: str):  # type: ignore[no-untyped-def]
        @activity.defn(name=name)
        async def run(raw: dict[str, Any]) -> dict[str, Any]:
            return {
                "schema_version": "amra.sat-activity-result.v1",
                "result_digest": digest(name),
                "checkpoint": name,
            }

        return run

    activities = [
        freeze,
        ordinary("solve_cnf"),
        ordinary("verify_and_record_evidence"),
        ordinary("finalize_execution_manifest"),
        ordinary("reconcile_cost"),
    ]
    async with (
        await WorkflowEnvironment.start_time_skipping() as environment,
        Worker(
            environment.client,
            task_queue="amra-cancel",
            workflows=[SatVerificationWorkflow],
            activities=activities,
        ),
    ):
        handle = await environment.client.start_workflow(
            SatVerificationWorkflow.run,
            payload(),
            id="cancel-signal",
            task_queue="amra-cancel",
        )
        await gate.wait()
        await handle.signal(
            SatVerificationWorkflow.cancel,
            {"reason": "operator request", "actor": "tester"},
        )
        with pytest.raises(WorkflowFailureError):
            await handle.result()


@pytest.mark.asyncio
async def test_hold_resume_and_timeout_retry_classification() -> None:
    freeze_started = asyncio.Event()
    release_freeze = asyncio.Event()
    timeout_attempts = 0

    @activity.defn(name="freeze_and_reserve")
    async def freeze(raw: dict[str, Any]) -> dict[str, Any]:
        freeze_started.set()
        await release_freeze.wait()
        return {
            "schema_version": "amra.sat-activity-result.v1",
            "result_digest": digest("freeze"),
            "checkpoint": "freeze",
        }

    @activity.defn(name="solve_cnf")
    async def timeout_then_solve(raw: dict[str, Any]) -> dict[str, Any]:
        nonlocal timeout_attempts
        timeout_attempts += 1
        if timeout_attempts == 1:
            raise TimeoutError("simulated infrastructure timeout")
        return {
            "schema_version": "amra.sat-activity-result.v1",
            "result_digest": digest("solve"),
            "checkpoint": "solve",
        }

    def ordinary(name: str):  # type: ignore[no-untyped-def]
        @activity.defn(name=name)
        async def run(raw: dict[str, Any]) -> dict[str, Any]:
            return {
                "schema_version": "amra.sat-activity-result.v1",
                "result_digest": digest(name),
                "checkpoint": name,
            }

        return run

    async with (
        await WorkflowEnvironment.start_time_skipping() as environment,
        Worker(
            environment.client,
            task_queue="amra-hold-timeout",
            workflows=[SatVerificationWorkflow],
            activities=[
                freeze,
                timeout_then_solve,
                ordinary("verify_and_record_evidence"),
                ordinary("finalize_execution_manifest"),
                ordinary("reconcile_cost"),
            ],
        ),
    ):
        handle = await environment.client.start_workflow(
            SatVerificationWorkflow.run,
            payload(),
            id="hold-timeout",
            task_queue="amra-hold-timeout",
        )
        await freeze_started.wait()
        await handle.signal(
            SatVerificationWorkflow.hold,
            {"reason": "inspect evidence boundary", "actor": "tester"},
        )
        release_freeze.set()
        await asyncio.sleep(0.1)
        status = await handle.query(SatVerificationWorkflow.status)
        assert status["held"] is True
        await handle.signal(
            SatVerificationWorkflow.resume,
            {"reason": "inspection complete", "actor": "tester"},
        )
        result = await handle.result()
    assert result["state"] == "SUCCEEDED"
    assert timeout_attempts == 2
