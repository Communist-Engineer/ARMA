from __future__ import annotations

import os
from datetime import UTC, datetime
from uuid import uuid4

import boto3
import pytest

from amra.adapters.artifacts.s3 import S3ArtifactStore
from amra.adapters.clock import FixedClock


@pytest.mark.integration
def test_pinned_minio_conditional_publication() -> None:
    endpoint = os.environ.get("AMRA_TEST_S3_ENDPOINT")
    if endpoint is None:
        pytest.skip("AMRA_TEST_S3_ENDPOINT is unset")
    client = boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=os.environ.get("AMRA_TEST_S3_ACCESS_KEY", "amra"),
        aws_secret_access_key=os.environ.get("AMRA_TEST_S3_SECRET_KEY", "amra-phase1-local"),
        region_name="us-east-1",
    )
    bucket = f"amra-integration-{uuid4()}"
    client.create_bucket(Bucket=bucket)
    store = S3ArtifactStore(
        client,
        bucket,
        "objects",
        FixedClock(datetime(2026, 8, 12, tzinfo=UTC)),
    )
    first = store.put_if_absent(b"equal", media_type="text/plain", actor="integration")
    second = store.put_if_absent(b"equal", media_type="text/plain", actor="integration")
    assert first.digest == second.digest
    assert store.read(first.digest) == b"equal"
