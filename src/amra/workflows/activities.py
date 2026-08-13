"""Activity contracts with explicit idempotency and heartbeat checkpoints."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from temporalio import activity

from amra.workflows.models import ActivityCommand, ActivityResult

ActivityHandler = Callable[[ActivityCommand], Awaitable[ActivityResult]]


class SatActivities:
    """Delegate infrastructure work while preserving one payload contract."""

    def __init__(self, handlers: dict[str, ActivityHandler]) -> None:
        self._handlers = handlers

    async def _run(self, name: str, raw: dict[str, Any]) -> dict[str, Any]:
        command = ActivityCommand.model_validate(raw)
        activity.heartbeat(
            {
                "idempotency_key": command.idempotency_key,
                "prior_result_digest": command.prior_result_digest,
            }
        )
        result = await self._handlers[name](command)
        return result.model_dump(mode="json")

    @activity.defn(name="freeze_and_reserve")
    async def freeze_and_reserve(self, raw: dict[str, Any]) -> dict[str, Any]:
        return await self._run("freeze_and_reserve", raw)

    @activity.defn(name="solve_cnf")
    async def solve_cnf(self, raw: dict[str, Any]) -> dict[str, Any]:
        return await self._run("solve_cnf", raw)

    @activity.defn(name="verify_and_record_evidence")
    async def verify_and_record_evidence(self, raw: dict[str, Any]) -> dict[str, Any]:
        return await self._run("verify_and_record_evidence", raw)

    @activity.defn(name="finalize_execution_manifest")
    async def finalize_execution_manifest(self, raw: dict[str, Any]) -> dict[str, Any]:
        return await self._run("finalize_execution_manifest", raw)

    @activity.defn(name="reconcile_cost")
    async def reconcile_cost(self, raw: dict[str, Any]) -> dict[str, Any]:
        return await self._run("reconcile_cost", raw)
