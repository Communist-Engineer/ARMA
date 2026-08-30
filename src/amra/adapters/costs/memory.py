"""Append-only in-memory synthetic price-book adapter."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from amra.domain.budget import ZERO, CostEvent, CostState, Money
from amra.domain.errors import (
    BudgetExhausted,
    DuplicateIdempotencyConflict,
    InvariantViolation,
)


@dataclass(frozen=True, slots=True)
class BudgetPolicy:
    category_limits: dict[str, Money]
    protected_verification_reserve: Money
    maximum_frontier_calls: int = 0


class InMemoryCostLedger:
    """Model reservation, debit, release, reconciliation, and quarantine events."""

    def __init__(self, policy: BudgetPolicy) -> None:
        self._policy = policy
        self._events: list[CostEvent] = []
        self._by_key: dict[str, tuple[object, ...]] = {}

    def _remember(self, key: str, signature: tuple[object, ...], event: CostEvent) -> CostEvent:
        previous = self._by_key.get(key)
        if previous is not None:
            if previous != signature:
                raise DuplicateIdempotencyConflict(f"cost key {key!r} has conflicting semantics")
            return next(item for item in self._events if item.idempotency_key == key)
        self._by_key[key] = signature
        self._events.append(event)
        return event

    def _category_committed(self, category: str) -> Decimal:
        reservations = sum(
            (
                event.amount.amount
                for event in self._events
                if event.category == category and event.state is CostState.RESERVED
            ),
            ZERO,
        )
        releases = sum(
            (
                event.amount.amount
                for event in self._events
                if event.category == category and event.state is CostState.RELEASED
            ),
            ZERO,
        )
        return reservations - releases

    def reserve(self, category: str, worst_case: Money, idempotency_key: str) -> CostEvent:
        limit = self._policy.category_limits.get(category)
        if limit is None:
            raise InvariantViolation(f"budget category {category!r} is undefined")
        if worst_case.currency != limit.currency:
            raise InvariantViolation("reservation currency differs from budget currency")
        allowed = limit.amount
        if category == "verification":
            allowed += self._policy.protected_verification_reserve.amount
        if self._category_committed(category) + worst_case.amount > allowed:
            raise BudgetExhausted(f"{category} reservation exceeds its envelope")
        event = CostEvent(CostState.RESERVED, worst_case, category, idempotency_key)
        return self._remember(
            idempotency_key,
            (CostState.RESERVED, category, worst_case.amount, worst_case.currency),
            event,
        )

    def reconcile(
        self,
        reservation_key: str,
        actual: Money,
        idempotency_key: str,
    ) -> tuple[CostEvent, ...]:
        reservation = next(
            (
                event
                for event in self._events
                if event.idempotency_key == reservation_key and event.state is CostState.RESERVED
            ),
            None,
        )
        if reservation is None:
            quarantine = CostEvent(
                CostState.QUARANTINED,
                actual,
                "unattributed",
                idempotency_key,
                reservation_key,
                "RESERVATION_NOT_FOUND",
            )
            return (
                self._remember(
                    idempotency_key,
                    (CostState.QUARANTINED, reservation_key, actual.amount, actual.currency),
                    quarantine,
                ),
            )
        if actual.currency != reservation.amount.currency:
            raise InvariantViolation("actual and reserved currencies differ")
        if actual.amount > reservation.amount.amount:
            raise BudgetExhausted("actual synthetic cost exceeds the worst-case reservation")
        debit = CostEvent(
            CostState.DEBITED,
            actual,
            reservation.category,
            f"{idempotency_key}:debit",
            reservation_key,
        )
        released = Money(
            reservation.amount.amount - actual.amount,
            reservation.amount.currency,
        )
        release = CostEvent(
            CostState.RELEASED,
            released,
            reservation.category,
            f"{idempotency_key}:release",
            reservation_key,
        )
        reconciled = CostEvent(
            CostState.RECONCILED,
            actual,
            reservation.category,
            idempotency_key,
            reservation_key,
        )
        signature = (CostState.RECONCILED, reservation_key, actual.amount, actual.currency)
        prior = self._by_key.get(idempotency_key)
        if prior is not None:
            if prior != signature:
                raise DuplicateIdempotencyConflict(
                    f"cost key {idempotency_key!r} has conflicting semantics"
                )
            return tuple(
                event
                for event in self._events
                if event.idempotency_key
                in {f"{idempotency_key}:debit", f"{idempotency_key}:release", idempotency_key}
            )
        self._remember(
            debit.idempotency_key,
            (CostState.DEBITED, reservation_key, actual.amount, actual.currency),
            debit,
        )
        self._remember(
            release.idempotency_key,
            (CostState.RELEASED, reservation_key, released.amount, released.currency),
            release,
        )
        self._remember(idempotency_key, signature, reconciled)
        return debit, release, reconciled

    def events(self) -> tuple[CostEvent, ...]:
        return tuple(self._events)
