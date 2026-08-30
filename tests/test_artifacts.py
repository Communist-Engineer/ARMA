from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from amra.adapters.artifacts.local import LocalArtifactStore
from amra.adapters.artifacts.s3 import S3ArtifactStore
from amra.adapters.clock import FixedClock
from amra.domain.errors import ArtifactConflict, ArtifactCorruption
from amra.domain.identifiers import Sha256Digest

NOW = datetime(2026, 8, 12, tzinfo=UTC)


def test_local_put_read_equal_concurrency_and_conflict(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path, FixedClock(NOW))
    content = b"frozen scientific bytes"
    with ThreadPoolExecutor(max_workers=8) as executor:
        records = list(
            executor.map(
                lambda _: store.put_if_absent(
                    content,
                    media_type="application/octet-stream",
                    actor="test",
                ),
                range(16),
            )
        )
    assert len({record.digest for record in records}) == 1
    digest = records[0].digest
    assert store.read(digest) == content
    with pytest.raises(ArtifactConflict):
        store.put_if_absent(
            b"other",
            media_type="application/octet-stream",
            actor="test",
            expected_digest=digest,
        )


def test_local_corruption_interrupted_temp_and_missing_object(tmp_path: Path) -> None:
    store = LocalArtifactStore(tmp_path, FixedClock(NOW))
    metadata = store.put_if_absent(b"sound", media_type="text/plain", actor="test")
    data_path = Path(metadata.storage_uri.removeprefix("file://"))
    (data_path.parent / ".amra-put-interrupted").write_bytes(b"partial")
    data_path.write_bytes(b"corrupt")
    with pytest.raises(ArtifactCorruption):
        store.read(metadata.digest)
    with pytest.raises(FileNotFoundError):
        store.read(Sha256Digest.from_bytes(b"absent"))


class Body:
    def __init__(self, content: bytes) -> None:
        self.content = content

    def read(self) -> bytes:
        return self.content


class FakeS3:
    def __init__(self) -> None:
        self.objects: dict[str, tuple[bytes, dict[str, str], str]] = {}

    def put_object(self, **kwargs: Any) -> None:
        key = kwargs["Key"]
        if key in self.objects:
            raise ClientError(
                {
                    "Error": {"Code": "PreconditionFailed"},
                    "ResponseMetadata": {"HTTPStatusCode": 412},
                },
                "PutObject",
            )
        self.objects[key] = (kwargs["Body"], kwargs["Metadata"], kwargs["ContentType"])

    def get_object(self, **kwargs: Any) -> dict[str, object]:
        return {"Body": Body(self.objects[kwargs["Key"]][0])}

    def head_object(self, **kwargs: Any) -> dict[str, object]:
        content, metadata, media_type = self.objects[kwargs["Key"]]
        return {
            "ContentLength": len(content),
            "ContentType": media_type,
            "LastModified": NOW,
            "Metadata": metadata,
        }


def test_s3_conditional_equal_write_and_corruption() -> None:
    client = FakeS3()
    store = S3ArtifactStore(client, "amra", "objects", FixedClock(NOW))
    record = store.put_if_absent(b"commons", media_type="text/plain", actor="test")
    assert (
        store.put_if_absent(b"commons", media_type="text/plain", actor="test").digest
        == record.digest
    )
    assert store.verify(record.digest).storage_uri.startswith("s3://amra/")
    key = next(iter(client.objects))
    _, metadata, media_type = client.objects[key]
    client.objects[key] = (b"enclosure", metadata, media_type)
    with pytest.raises(ArtifactCorruption):
        store.read(record.digest)
