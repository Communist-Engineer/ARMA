"""Content-addressed artifact port."""

from __future__ import annotations

from typing import Protocol

from amra.domain.artifacts import ArtifactMetadata
from amra.domain.identifiers import Sha256Digest


class ArtifactPort(Protocol):
    def put_if_absent(
        self,
        content: bytes,
        *,
        media_type: str,
        actor: str,
        retention_class: str = "STANDARD",
        expected_digest: Sha256Digest | None = None,
    ) -> ArtifactMetadata: ...

    def read(self, digest: Sha256Digest) -> bytes: ...

    def verify(self, digest: Sha256Digest) -> ArtifactMetadata: ...
