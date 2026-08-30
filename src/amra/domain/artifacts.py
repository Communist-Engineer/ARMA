"""Artifact metadata with content-addressed identity."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from amra.domain.errors import InvariantViolation
from amra.domain.identifiers import Sha256Digest


@dataclass(frozen=True, slots=True)
class ArtifactMetadata:
    digest: Sha256Digest
    media_type: str
    size_bytes: int
    created_actor: str
    storage_uri: str
    retention_class: str
    created_at: datetime

    def __post_init__(self) -> None:
        if self.size_bytes < 0:
            raise InvariantViolation("artifact size must be nonnegative")
        if self.created_at.tzinfo is None:
            raise InvariantViolation("artifact creation time must be timezone-aware")
        for value, label in (
            (self.media_type, "media type"),
            (self.created_actor, "creation actor"),
            (self.storage_uri, "storage URI"),
            (self.retention_class, "retention class"),
        ):
            if not value:
                raise InvariantViolation(f"artifact {label} is required")
