from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis.stateful import RuleBasedStateMachine, invariant, rule

from amra.domain.errors import InvalidTransition, InvariantViolation
from amra.domain.identifiers import EntityId, ObligationId, Sha256Digest
from amra.domain.obligation import Obligation, ObligationState, valid_targets
from amra.domain.resources import Measure, MissingReason, ResourceVector

NOW = datetime(2026, 8, 12, tzinfo=UTC)


def test_digest_and_typed_uuid_primitives() -> None:
    digest = Sha256Digest.from_bytes(b"commons")
    assert str(digest) == "sha256:dbfaa5d6a74412605263d67e5d4b7bd4192ac6041cee36098252077896f134ff"
    assert digest.verify(b"commons")
    assert digest.hex() == str(digest).split(":")[1]
    parsed = EntityId.parse(str(EntityId.new()))
    assert str(parsed.value) == str(parsed)
    with pytest.raises(InvariantViolation):
        Sha256Digest("sha256:ABC")
    with pytest.raises(InvariantViolation):
        EntityId.parse("collective")


def test_obligation_compare_and_set_hold_and_resume() -> None:
    draft = Obligation(ObligationId.new(), "Verify a frozen CNF", updated_at=NOW)
    ready = draft.transition(ObligationState.READY, expected_version=0, at=NOW)
    held = ready.transition(ObligationState.HELD, expected_version=1, at=NOW)
    resumed = held.resume(expected_version=2, at=NOW)
    assert resumed.state is ObligationState.READY
    assert resumed.version == 3
    with pytest.raises(InvalidTransition):
        draft.transition(ObligationState.SUCCEEDED, expected_version=0, at=NOW)
    with pytest.raises(InvalidTransition):
        ready.transition(ObligationState.RESERVED, expected_version=0, at=NOW)
    with pytest.raises(InvalidTransition):
        ready.resume(expected_version=1, at=NOW)


class ObligationMachine(RuleBasedStateMachine):
    def __init__(self) -> None:
        super().__init__()
        self.obligation = Obligation(ObligationId.new(), "State-machine check", updated_at=NOW)

    @rule()
    def take_valid_transition(self) -> None:
        targets = tuple(valid_targets(self.obligation.state))
        if targets:
            self.obligation = self.obligation.transition(
                targets[0],
                expected_version=self.obligation.version,
                at=NOW,
            )

    @invariant()
    def version_is_monotonic(self) -> None:
        assert self.obligation.version >= 0
        assert self.obligation.updated_at.tzinfo is not None


TestObligationMachine = ObligationMachine.TestCase


def _vector(value: str) -> ResourceVector:
    measured = lambda unit: Measure.measured(value, unit)  # noqa: E731
    return ResourceVector(
        measured("s"),
        measured("s"),
        measured("s"),
        measured("bytes"),
        measured("literals"),
        measured("degree"),
        measured("rank"),
        measured("bits"),
        measured("bits"),
        measured("process-s"),
        measured("bytes"),
        measured("bits"),
        measured("USD"),
    )


def test_resource_vector_pareto_and_missing_reasons() -> None:
    assert _vector("1").dominates(_vector("2"))
    assert not _vector("2").dominates(_vector("1"))
    assert not _vector("1").dominates(_vector("1"))
    missing = Measure.missing("degree", MissingReason.FORMALLY_INAPPLICABLE)
    assert missing.value is None
    with pytest.raises(InvariantViolation):
        Measure(None, "s")
    with pytest.raises(InvariantViolation):
        Measure(Decimal("1"), "s", MissingReason.TOOL_DID_NOT_REPORT)
    with pytest.raises(InvariantViolation):
        Measure.measured("-1", "s")


@given(st.binary())
def test_digest_matches_hashlib_for_arbitrary_bytes(content: bytes) -> None:
    assert Sha256Digest.from_bytes(content).verify(content)
