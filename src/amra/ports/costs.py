"""Budget reservation and reconciliation port."""

from typing import Protocol

from amra.domain.budget import CostEvent, Money


class CostPort(Protocol):
    def reserve(self, category: str, worst_case: Money, idempotency_key: str) -> CostEvent: ...

    def reconcile(
        self,
        reservation_key: str,
        actual: Money,
        idempotency_key: str,
    ) -> tuple[CostEvent, ...]: ...

    def events(self) -> tuple[CostEvent, ...]: ...
