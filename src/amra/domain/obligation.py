"""Obligation lifecycle and compare-and-set transitions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from amra.domain.errors import InvalidTransition, InvariantViolation
from amra.domain.identifiers import ObligationId, Sha256Digest


class ObligationState(StrEnum):
    DRAFT = "DRAFT"
    READY = "READY"
    RESERVED = "RESERVED"
    RUNNING = "RUNNING"
    AWAITING_EVIDENCE = "AWAITING_EVIDENCE"
    AWAITING_REVIEW = "AWAITING_REVIEW"
    AWAITING_HUMAN = "AWAITING_HUMAN"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    HELD = "HELD"


_TRANSITIONS: Mapping[ObligationState, frozenset[ObligationState]] = MappingProxyType(
    {
        ObligationState.DRAFT: frozenset({ObligationState.READY, ObligationState.CANCELLED}),
        ObligationState.READY: frozenset(
            {ObligationState.RESERVED, ObligationState.CANCELLED, ObligationState.HELD}
        ),
        ObligationState.RESERVED: frozenset(
            {ObligationState.RUNNING, ObligationState.CANCELLED, ObligationState.HELD}
        ),
        ObligationState.RUNNING: frozenset(
            {
                ObligationState.AWAITING_EVIDENCE,
                ObligationState.FAILED,
                ObligationState.CANCELLED,
                ObligationState.HELD,
            }
        ),
        ObligationState.AWAITING_EVIDENCE: frozenset(
            {
                ObligationState.AWAITING_REVIEW,
                ObligationState.SUCCEEDED,
                ObligationState.FAILED,
                ObligationState.HELD,
            }
        ),
        ObligationState.AWAITING_REVIEW: frozenset(
            {
                ObligationState.AWAITING_HUMAN,
                ObligationState.SUCCEEDED,
                ObligationState.FAILED,
                ObligationState.HELD,
            }
        ),
        ObligationState.AWAITING_HUMAN: frozenset(
            {ObligationState.SUCCEEDED, ObligationState.FAILED, ObligationState.HELD}
        ),
        ObligationState.HELD: frozenset(
            {
                ObligationState.READY,
                ObligationState.RESERVED,
                ObligationState.RUNNING,
                ObligationState.AWAITING_EVIDENCE,
                ObligationState.AWAITING_REVIEW,
                ObligationState.AWAITING_HUMAN,
                ObligationState.CANCELLED,
                ObligationState.FAILED,
            }
        ),
        ObligationState.SUCCEEDED: frozenset(),
        ObligationState.FAILED: frozenset(),
        ObligationState.CANCELLED: frozenset(),
    }
)


@dataclass(frozen=True, slots=True)
class Obligation:
    id: ObligationId
    objective: str
    state: ObligationState = ObligationState.DRAFT
    version: int = 0
    packet_digest: Sha256Digest | None = None
    policy_version: str = "0.1.0"
    updated_at: datetime = field(default_factory=lambda: datetime.min.replace(tzinfo=UTC))
    held_from: ObligationState | None = None

    def __post_init__(self) -> None:
        if not self.objective.strip():
            raise InvariantViolation("objective must contain substantive text")
        if self.version < 0:
            raise InvariantViolation("object version must be nonnegative")
        if self.updated_at.tzinfo is None:
            raise InvariantViolation("updated_at must be timezone-aware")

    def transition(
        self,
        target: ObligationState,
        *,
        expected_version: int,
        at: datetime,
    ) -> Obligation:
        if expected_version != self.version:
            raise InvalidTransition(
                "compare-and-set version mismatch: "
                f"expected {expected_version}, actual {self.version}"
            )
        if at.tzinfo is None:
            raise InvariantViolation("transition timestamp must be timezone-aware")
        if target not in _TRANSITIONS[self.state]:
            raise InvalidTransition(f"transition {self.state.value}->{target.value} is undefined")
        held_from = self.state if target is ObligationState.HELD else None
        return replace(
            self,
            state=target,
            version=self.version + 1,
            updated_at=at,
            held_from=held_from,
        )

    def resume(self, *, expected_version: int, at: datetime) -> Obligation:
        if self.state is not ObligationState.HELD or self.held_from is None:
            raise InvalidTransition("resume requires an obligation held from a resumable state")
        return self.transition(self.held_from, expected_version=expected_version, at=at)

    def with_packet(self, digest: Sha256Digest) -> Obligation:
        if self.state is not ObligationState.DRAFT:
            raise InvalidTransition("packet freezing is defined only for draft obligations")
        return replace(self, packet_digest=digest)


def valid_targets(state: ObligationState) -> frozenset[ObligationState]:
    return _TRANSITIONS[state]
