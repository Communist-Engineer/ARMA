"""Authoritative domain ledger port."""

from typing import Protocol

from amra.domain.obligation import Obligation


class LedgerPort(Protocol):
    def create_obligation(self, obligation: Obligation, idempotency_key: str) -> Obligation: ...

    def get_obligation(self, obligation_id: str) -> Obligation: ...

    def compare_and_set_obligation(
        self,
        obligation: Obligation,
        expected_version: int,
        idempotency_key: str,
    ) -> Obligation: ...
