"""Crash-conscious content-addressed local artifact storage."""

from __future__ import annotations

import fcntl
import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

from amra.adapters.artifacts.canonical import canonical_json_bytes
from amra.domain.artifacts import ArtifactMetadata
from amra.domain.errors import ArtifactConflict, ArtifactCorruption
from amra.domain.identifiers import Sha256Digest
from amra.ports.clock import ClockPort

_DIR_MODE: Final = 0o750


class LocalArtifactStore:
    """Publish immutable bytes using flush, fsync, rename, and verified reads."""

    def __init__(self, root: Path, clock: ClockPort) -> None:
        self._root = root.resolve()
        self._clock = clock
        self._root.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)

    def _data_path(self, digest: Sha256Digest) -> Path:
        return self._root / "sha256" / digest.hex()[:2] / digest.hex()[2:]

    @staticmethod
    def _metadata_path(data_path: Path) -> Path:
        return data_path.with_name(f"{data_path.name}.metadata.json")

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        descriptor = os.open(directory, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)

    @classmethod
    def _atomic_publish(cls, target: Path, content: bytes) -> None:
        target.parent.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(prefix=".amra-put-", dir=target.parent)
        temporary = Path(temporary_name)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
            cls._fsync_directory(target.parent)
        finally:
            temporary.unlink(missing_ok=True)

    def put_if_absent(
        self,
        content: bytes,
        *,
        media_type: str,
        actor: str,
        retention_class: str = "STANDARD",
        expected_digest: Sha256Digest | None = None,
    ) -> ArtifactMetadata:
        digest = Sha256Digest.from_bytes(content)
        if expected_digest is not None and digest != expected_digest:
            raise ArtifactConflict(
                f"declared {expected_digest} differs from content identity {digest}"
            )
        target = self._data_path(digest)
        target.parent.mkdir(mode=_DIR_MODE, parents=True, exist_ok=True)
        lock_path = target.with_name(f"{target.name}.lock")
        with lock_path.open("a+b") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            if target.exists():
                existing = target.read_bytes()
                if existing != content or not digest.verify(existing):
                    raise ArtifactConflict(f"existing bytes conflict at {digest}")
                return self.verify(digest)

            created_at = self._clock.now()
            metadata = ArtifactMetadata(
                digest=digest,
                media_type=media_type,
                size_bytes=len(content),
                created_actor=actor,
                storage_uri=target.as_uri(),
                retention_class=retention_class,
                created_at=created_at,
            )
            self._atomic_publish(target, content)
            serialized_metadata = canonical_json_bytes(
                {
                    "created_actor": metadata.created_actor,
                    "created_at": metadata.created_at.astimezone(UTC)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "digest": str(metadata.digest),
                    "media_type": metadata.media_type,
                    "retention_class": metadata.retention_class,
                    "size_bytes": metadata.size_bytes,
                    "storage_uri": metadata.storage_uri,
                }
            )
            self._atomic_publish(self._metadata_path(target), serialized_metadata)
            self.read(digest)
            return metadata

    def read(self, digest: Sha256Digest) -> bytes:
        target = self._data_path(digest)
        try:
            content = target.read_bytes()
        except FileNotFoundError:
            raise FileNotFoundError(f"artifact {digest} is missing") from None
        if not digest.verify(content):
            raise ArtifactCorruption(f"artifact {digest} failed read-time digest verification")
        return content

    def verify(self, digest: Sha256Digest) -> ArtifactMetadata:
        content = self.read(digest)
        metadata_path = self._metadata_path(self._data_path(digest))
        try:
            raw = json.loads(metadata_path.read_bytes())
            created_at = datetime.fromisoformat(str(raw["created_at"]).replace("Z", "+00:00"))
            metadata = ArtifactMetadata(
                digest=Sha256Digest(str(raw["digest"])),
                media_type=str(raw["media_type"]),
                size_bytes=int(raw["size_bytes"]),
                created_actor=str(raw["created_actor"]),
                storage_uri=str(raw["storage_uri"]),
                retention_class=str(raw["retention_class"]),
                created_at=created_at,
            )
        except (FileNotFoundError, KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise ArtifactCorruption(f"metadata for artifact {digest} is invalid") from error
        if metadata.digest != digest or metadata.size_bytes != len(content):
            raise ArtifactCorruption(f"metadata for artifact {digest} conflicts with stored bytes")
        return metadata
