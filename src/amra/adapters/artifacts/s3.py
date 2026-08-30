"""S3-compatible put-if-absent artifact adapter."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from botocore.exceptions import ClientError

from amra.domain.artifacts import ArtifactMetadata
from amra.domain.errors import ArtifactConflict, ArtifactCorruption
from amra.domain.identifiers import Sha256Digest
from amra.ports.clock import ClockPort


class S3ArtifactStore:
    """Use conditional object creation and verify every scientific read."""

    def __init__(self, client: Any, bucket: str, prefix: str, clock: ClockPort) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._clock = clock

    def _key(self, digest: Sha256Digest) -> str:
        suffix = f"sha256/{digest.hex()[:2]}/{digest.hex()[2:]}"
        return f"{self._prefix}/{suffix}" if self._prefix else suffix

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
        key = self._key(digest)
        created_at = self._clock.now()
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=content,
                ContentType=media_type,
                IfNoneMatch="*",
                Metadata={
                    "amra-sha256": digest.hex(),
                    "created-actor": actor,
                    "retention-class": retention_class,
                },
            )
        except ClientError as error:
            response: dict[str, Any] = error.response
            status = int(response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0))
            code = str(response.get("Error", {}).get("Code", ""))
            if status not in {409, 412} and code not in {
                "PreconditionFailed",
                "ConditionalRequestConflict",
            }:
                raise
            if self.read(digest) != content:
                raise ArtifactConflict(f"existing S3 bytes conflict at {digest}") from error
        self.read(digest)
        return ArtifactMetadata(
            digest=digest,
            media_type=media_type,
            size_bytes=len(content),
            created_actor=actor,
            storage_uri=f"s3://{self._bucket}/{key}",
            retention_class=retention_class,
            created_at=created_at,
        )

    def read(self, digest: Sha256Digest) -> bytes:
        response = self._client.get_object(Bucket=self._bucket, Key=self._key(digest))
        content = response["Body"].read()
        if not isinstance(content, bytes) or not digest.verify(content):
            raise ArtifactCorruption(f"artifact {digest} failed S3 read-time digest verification")
        return content

    def verify(self, digest: Sha256Digest) -> ArtifactMetadata:
        content = self.read(digest)
        response = self._client.head_object(Bucket=self._bucket, Key=self._key(digest))
        metadata = response.get("Metadata", {})
        modified = response.get("LastModified", self._clock.now())
        if not isinstance(modified, datetime):
            raise ArtifactCorruption(f"artifact {digest} has an invalid S3 timestamp")
        return ArtifactMetadata(
            digest=digest,
            media_type=str(response.get("ContentType", "application/octet-stream")),
            size_bytes=len(content),
            created_actor=str(metadata.get("created-actor", "unknown")),
            storage_uri=f"s3://{self._bucket}/{self._key(digest)}",
            retention_class=str(metadata.get("retention-class", "STANDARD")),
            created_at=modified,
        )
