"""Deterministic in-memory ledger for unit tests and the local demonstration."""

from __future__ import annotations

from amra.domain.errors import DuplicateIdempotencyConflict, InvalidTransition
from amra.domain.obligation import Obligation


class InMemoryLedger:
    def __init__(self) -> None:
        self._obligations: dict[str, Obligation] = {}
        self._operations: dict[str, tuple[object, ...]] = {}

    def _deduplicate(self, key: str, signature: tuple[object, ...]) -> bool:
        existing = self._operations.get(key)
        if existing is None:
            self._operations[key] = signature
            return False
        if existing != signature:
            raise DuplicateIdempotencyConflict(f"ledger key {key!r} has conflicting semantics")
        return True

    def create_obligation(self, obligation: Obligation, idempotency_key: str) -> Obligation:
        signature = ("create", str(obligation.id), obligation.objective)
        if self._deduplicate(idempotency_key, signature):
            return self._obligations[str(obligation.id)]
        if str(obligation.id) in self._obligations:
            raise DuplicateIdempotencyConflict("obligation identity already exists")
        self._obligations[str(obligation.id)] = obligation
        return obligation

    def get_obligation(self, obligation_id: str) -> Obligation:
        return self._obligations[obligation_id]

    def compare_and_set_obligation(
        self,
        obligation: Obligation,
        expected_version: int,
        idempotency_key: str,
    ) -> Obligation:
        signature = (
            "cas",
            str(obligation.id),
            expected_version,
            obligation.version,
            obligation.state,
        )
        if self._deduplicate(idempotency_key, signature):
            return self._obligations[str(obligation.id)]
        current = self._obligations[str(obligation.id)]
        if current.version != expected_version:
            raise InvalidTransition(
                f"ledger compare-and-set expected {expected_version}, actual {current.version}"
            )
        self._obligations[str(obligation.id)] = obligation
        return obligation
