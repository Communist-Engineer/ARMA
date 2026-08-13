"""Validated identifiers used by the immutable domain core."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Self
from uuid import UUID, uuid4

from amra.domain.errors import InvariantViolation

_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


@dataclass(frozen=True, slots=True, order=True)
class Sha256Digest:
    """A content identity with an explicit algorithm prefix."""

    value: str

    def __post_init__(self) -> None:
        if _DIGEST_RE.fullmatch(self.value) is None:
            raise InvariantViolation("digest must match sha256:<64 lowercase hex>")

    @classmethod
    def from_bytes(cls, content: bytes) -> Self:
        return cls(f"sha256:{hashlib.sha256(content).hexdigest()}")

    def verify(self, content: bytes) -> bool:
        return self == type(self).from_bytes(content)

    def hex(self) -> str:
        return self.value.removeprefix("sha256:")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True, order=True)
class EntityId:
    """Typed UUID wrapper for durable domain identities."""

    value: UUID

    @classmethod
    def new(cls) -> Self:
        return cls(uuid4())

    @classmethod
    def parse(cls, value: str) -> Self:
        try:
            return cls(UUID(value))
        except ValueError as error:
            raise InvariantViolation("identifier must be a valid UUID") from error

    def __str__(self) -> str:
        return str(self.value)


class ObligationId(EntityId):
    """Identity for one durable scientific obligation."""


class AttemptId(EntityId):
    """Identity for one execution attempt."""


class EvidenceId(EntityId):
    """Identity for one immutable evidence record."""
