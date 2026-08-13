from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi.testclient import TestClient

from amra.adapters.artifacts.local import LocalArtifactStore
from amra.adapters.clock import FixedClock
from amra.api.app import create_app


def client(tmp_path: Path) -> TestClient:
    store = LocalArtifactStore(tmp_path, FixedClock(datetime(2026, 8, 12, tzinfo=UTC)))
    return TestClient(create_app(store))


def test_artifact_and_obligation_idempotency(tmp_path: Path) -> None:
    http = client(tmp_path)
    content = b"p cnf 1 1\n1 0\n"
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    initiated = http.post(
        "/v1/artifacts:initiate",
        headers={"Idempotency-Key": "init"},
        json={
            "digest": digest,
            "media_type": "application/x-dimacs-cnf",
            "size_bytes": len(content),
        },
    )
    assert initiated.status_code == 200
    assert (
        http.post(
            "/v1/artifacts:initiate",
            headers={"Idempotency-Key": "init"},
            json={
                "digest": digest,
                "media_type": "application/x-dimacs-cnf",
                "size_bytes": len(content),
            },
        ).json()
        == initiated.json()
    )
    finalized = http.post(
        "/v1/artifacts:finalize",
        headers={"Idempotency-Key": "finalize"},
        json={
            "upload_id": initiated.json()["upload_id"],
            "digest": digest,
            "content_base64": base64.b64encode(content).decode(),
            "created_actor": "test",
        },
    )
    assert finalized.status_code == 200
    created = http.post(
        "/v1/obligations",
        headers={"Idempotency-Key": "create"},
        json={"objective": "Verify fixture", "cnf_digest": digest},
    )
    assert created.status_code == 200
    obligation_id = created.json()["id"]
    frozen = http.post(
        f"/v1/obligations/{obligation_id}:freeze",
        headers={"Idempotency-Key": "freeze"},
    )
    assert frozen.json()["state"] == "RESERVED"
    started = http.post(
        f"/v1/obligations/{obligation_id}:start",
        headers={"Idempotency-Key": "start"},
    )
    assert started.json()["state"] == "RUNNING"
    held = http.post(
        f"/v1/obligations/{obligation_id}:hold",
        headers={"Idempotency-Key": "hold"},
        json={"reason": "inspect", "actor": "tester"},
    )
    assert held.json()["state"] == "HELD"
    assert http.get(f"/v1/obligations/{obligation_id}").json()["object_version"] == 4
    assert http.get("/v1/costs").status_code == 200


def test_health_idempotency_header_and_openapi_snapshot(tmp_path: Path) -> None:
    http = client(tmp_path)
    assert http.get("/health/live").json()["status"] == "ok"
    assert http.get("/health/ready").json()["status"] == "ok"
    assert http.post("/v1/artifacts:initiate", json={}).status_code == 422
    canonical = json.dumps(http.app.openapi(), sort_keys=True, separators=(",", ":")).encode()
    expected = (Path(__file__).parents[1] / "schemas/openapi-v1.sha256").read_text().strip()
    assert hashlib.sha256(canonical).hexdigest() == expected
