"""Append-only synthetic cost accounting primitives."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum

from amra.domain.errors import InvariantViolation

ZERO = Decimal("0.000000")


class CostState(StrEnum):
    RESERVED = "RESERVED"
    DEBITED = "DEBITED"
    RELEASED = "RELEASED"
    RECONCILED = "RECONCILED"
    QUARANTINED = "QUARANTINED"


@dataclass(frozen=True, slots=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        if self.amount < ZERO:
            raise InvariantViolation("money amount must be nonnegative")
        if len(self.currency) != 3 or self.currency != self.currency.upper():
            raise InvariantViolation("currency must be a three-letter uppercase code")

    @classmethod
    def usd(cls, value: str | int | Decimal) -> Money:
        return cls(Decimal(value).quantize(Decimal("0.000001")), "USD")


@dataclass(frozen=True, slots=True)
class CostEvent:
    state: CostState
    amount: Money
    category: str
    idempotency_key: str
    reservation_key: str | None = None
    reason_code: str | None = None

    def __post_init__(self) -> None:
        if not self.category:
            raise InvariantViolation("cost category is required")
        if not self.idempotency_key:
            raise InvariantViolation("cost idempotency key is required")
