"""Durable workflow boundary."""

from typing import Protocol


class WorkflowPort(Protocol):
    async def start(self, obligation_id: str, manifest_digest: str) -> str: ...

    async def signal(self, workflow_id: str, signal: str, payload: dict[str, object]) -> None: ...

    async def query(self, workflow_id: str) -> dict[str, object]: ...
