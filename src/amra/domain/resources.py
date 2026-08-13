"""Complete resource vectors and Pareto comparison."""

from __future__ import annotations

from dataclasses import dataclass, fields
from decimal import Decimal
from enum import StrEnum
from typing import Self

from amra.domain.errors import InvariantViolation


class MissingReason(StrEnum):
    FORMALLY_INAPPLICABLE = "FORMALLY_INAPPLICABLE"
    INSTRUMENT_UNAVAILABLE = "INSTRUMENT_UNAVAILABLE"
    TOOL_DID_NOT_REPORT = "TOOL_DID_NOT_REPORT"


@dataclass(frozen=True, slots=True)
class Measure:
    value: Decimal | None
    unit: str
    missing_reason: MissingReason | None = None

    def __post_init__(self) -> None:
        if self.value is None and self.missing_reason is None:
            raise InvariantViolation("a null measure requires a reason code")
        if self.value is not None and self.missing_reason is not None:
            raise InvariantViolation("a measured value and missing reason are mutually exclusive")
        if self.value is not None and self.value < 0:
            raise InvariantViolation("resource values must be nonnegative")
        if not self.unit:
            raise InvariantViolation("resource unit is required")

    @classmethod
    def measured(cls, value: int | str | Decimal, unit: str) -> Self:
        return cls(Decimal(value), unit)

    @classmethod
    def missing(cls, unit: str, reason: MissingReason) -> Self:
        return cls(None, unit, reason)


@dataclass(frozen=True, slots=True)
class ResourceVector:
    discovery_time: Measure
    execution_time: Measure
    verification_time: Measure
    peak_memory: Measure
    width: Measure
    algebraic_degree: Measure
    rank: Measure
    precision_bits: Measure
    advice_bits: Measure
    aggregate_parallel_work: Measure
    communication_bytes: Measure
    random_bits: Measure
    monetary_cost: Measure
    extra_resources: tuple[tuple[str, Measure], ...] = ()

    def dominates(self, other: ResourceVector) -> bool:
        """Return strict Pareto dominance for equally measurable coordinates."""

        less_or_equal = True
        strictly_less = False
        for field in fields(self):
            if field.name == "extra_resources":
                continue
            left = getattr(self, field.name)
            right = getattr(other, field.name)
            if not isinstance(left, Measure) or not isinstance(right, Measure):
                raise InvariantViolation("resource coordinate must be a Measure")
            if left.unit != right.unit:
                raise InvariantViolation(f"unit mismatch for {field.name}")
            if left.value is None or right.value is None:
                return False
            less_or_equal &= left.value <= right.value
            strictly_less |= left.value < right.value
        if tuple(name for name, _ in self.extra_resources) != tuple(
            name for name, _ in other.extra_resources
        ):
            raise InvariantViolation("extra-resource coordinates must match for comparison")
        paired = zip(self.extra_resources, other.extra_resources, strict=True)
        for (name, left), (_, right) in paired:
            if left.unit != right.unit:
                raise InvariantViolation(f"unit mismatch for extra resource {name}")
            if left.value is None or right.value is None:
                return False
            less_or_equal &= left.value <= right.value
            strictly_less |= left.value < right.value
        return less_or_equal and strictly_less
