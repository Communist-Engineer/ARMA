"""Typed failures crossing AMRA application boundaries."""


class AmraError(Exception):
    """Base class for expected AMRA failures."""


class InvariantViolation(AmraError):
    """A domain invariant would be violated."""


class InvalidTransition(InvariantViolation):
    """An obligation lifecycle transition is outside the declared graph."""


class ArtifactConflict(InvariantViolation):
    """Stored content conflicts with a declared digest."""


class ArtifactCorruption(InvariantViolation):
    """Artifact bytes fail read-time digest verification."""


class BudgetExhausted(InvariantViolation):
    """A reservation exceeds its applicable envelope."""


class DuplicateIdempotencyConflict(InvariantViolation):
    """An idempotency key was reused for a different operation."""


class InvalidDimacs(InvariantViolation):
    """DIMACS input violates the strict parser contract."""


class InvalidAssignment(InvariantViolation):
    """A SAT assignment violates its syntax or semantic contract."""


class ExecutionFailure(AmraError):
    """An isolated external process failed its execution contract."""


class InvalidCertificate(AmraError):
    """An independently checked certificate was rejected."""
