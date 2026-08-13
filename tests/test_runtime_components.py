from __future__ import annotations

import hashlib
import json
import logging
import sys
from contextlib import nullcontext
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import Engine

from amra.adapters.execution.process import LocalProcessExecutor
from amra.adapters.postgres.health import validate_database_requirements
from amra.adapters.postgres.ledger import PostgresLedger
from amra.cli import main as cli
from amra.config import Settings
from amra.domain.errors import DuplicateIdempotencyConflict, InvalidTransition, InvariantViolation
from amra.domain.identifiers import ObligationId, Sha256Digest
from amra.domain.obligation import Obligation, ObligationState
from amra.observability import JsonTraceFormatter, configure_json_logging
from amra.ports.execution import ResourceLimits
from amra.workflows.activities import SatActivities
from amra.workflows.models import ActivityCommand, ActivityResult
from amra.workflows.worker import LocalActivityHandlers

FIXTURES = Path(__file__).parent / "fixtures"
TOOL_BIN = Path(__file__).parents[1] / "build" / "toolchain" / "bin"
NOW = datetime(2026, 8, 13, tzinfo=UTC)


class FakeResult:
    def __init__(
        self, value: object = None, *, row: dict[str, object] | None = None, rowcount: int = 1
    ):
        self.value = value
        self.row = row
        self.rowcount = rowcount

    def scalar_one_or_none(self) -> object:
        return self.value

    def scalar_one(self) -> object:
        return self.value

    def mappings(self) -> FakeResult:
        return self

    def one(self) -> dict[str, object]:
        assert self.row is not None
        return self.row

    def all(self) -> list[tuple[str, str]]:
        return cast(list[tuple[str, str]], self.value)


class FakeDatabase:
    def __init__(self) -> None:
        self.operations: dict[str, str] = {}
        self.obligations: dict[object, dict[str, object]] = {}

    def begin(self) -> nullcontext[FakeDatabase]:
        return nullcontext(self)

    def connect(self) -> nullcontext[FakeDatabase]:
        return nullcontext(self)

    def execute(self, statement: object, parameters: dict[str, object] | None = None) -> FakeResult:
        sql = str(statement)
        params = parameters or {}
        if sql.startswith("INSERT INTO idempotency_records"):
            key = str(params["key"])
            signature = hashlib.sha256(str(params["signature"]).encode()).hexdigest()
            if key in self.operations:
                return FakeResult(None)
            self.operations[key] = signature
            return FakeResult(key)
        if sql.startswith("SELECT operation_digest"):
            return FakeResult(self.operations[str(params["key"])])
        if sql.startswith("SELECT encode(digest"):
            return FakeResult(hashlib.sha256(str(params["signature"]).encode()).hexdigest())
        if sql.startswith("INSERT INTO obligations"):
            self.obligations[params["id"]] = {
                "id": params["id"],
                "objective": params["objective"],
                "state": params["state"],
                "state_version": params["version"],
                "packet_artifact_digest": None,
                "policy_versions": json.loads(str(params["policy"])),
                "updated_at": params["updated"],
            }
            return FakeResult()
        if sql.startswith("SELECT id, objective"):
            return FakeResult(row=self.obligations[params["id"]])
        if sql.startswith("UPDATE obligations"):
            row = self.obligations[params["id"]]
            if row["state_version"] != params["expected"]:
                return FakeResult(rowcount=0)
            row.update(
                state=params["state"],
                state_version=params["new_version"],
                packet_artifact_digest=params["packet"],
                updated_at=params["updated"],
            )
            return FakeResult(rowcount=1)
        raise AssertionError(sql)


def test_postgres_core_ledger_idempotency_and_compare_and_set() -> None:
    database = FakeDatabase()
    ledger = PostgresLedger(cast(Engine, database), uuid4())
    draft = Obligation(ObligationId.new(), "Core transaction", updated_at=NOW)
    assert ledger.create_obligation(draft, "create") == draft
    assert ledger.create_obligation(draft, "create") == draft
    database.operations["conflict"] = "different"
    with pytest.raises(DuplicateIdempotencyConflict):
        ledger.create_obligation(draft, "conflict")
    ready = draft.transition(ObligationState.READY, expected_version=0, at=NOW)
    assert ledger.compare_and_set_obligation(ready, 0, "ready") == ready
    assert ledger.compare_and_set_obligation(ready, 0, "ready") == ready
    running = ready.transition(ObligationState.RESERVED, expected_version=1, at=NOW)
    with pytest.raises(InvalidTransition):
        ledger.compare_and_set_obligation(running, 0, "stale")


@pytest.mark.parametrize(
    ("version", "extensions", "accepted"),
    [
        (180004, [("pgcrypto", "1.3"), ("vector", "0.8.6")], True),
        (170000, [("pgcrypto", "1.3"), ("vector", "0.8.6")], False),
        (180004, [("pgcrypto", "1.3")], False),
        (180004, [("pgcrypto", "1.3"), ("vector", "0.8.5")], False),
    ],
)
def test_database_readiness(
    version: int, extensions: list[tuple[str, str]], accepted: bool
) -> None:
    class Connection:
        calls = 0

        def execute(self, _: object) -> FakeResult:
            self.calls += 1
            return FakeResult(version if self.calls == 1 else extensions)

    if accepted:
        validate_database_requirements(cast(Any, Connection()))
    else:
        with pytest.raises(InvariantViolation):
            validate_database_requirements(cast(Any, Connection()))


def settings(tmp_path: Path) -> Settings:
    return Settings(
        artifact_root=tmp_path / "artifacts",
        workspace_root=tmp_path / "workspaces",
        cadical_path=TOOL_BIN / "cadical",
        drat_trim_path=TOOL_BIN / "drat-trim",
        cake_lpr_path=TOOL_BIN / "cake_lpr",
    )


@pytest.mark.asyncio
async def test_worker_journal_recovers_completed_scientific_work(tmp_path: Path) -> None:
    configuration = settings(tmp_path)
    configuration.workspace_root.mkdir(parents=True)
    handlers = LocalActivityHandlers(configuration)
    cnf = handlers.store.put_if_absent(
        (FIXTURES / "unsat.cnf").read_bytes(),
        media_type="application/x-dimacs-cnf",
        actor="test",
    )

    def command(stage: str, prior: str | None = None) -> ActivityCommand:
        return ActivityCommand(
            obligation_id=str(uuid4()),
            cnf_digest=str(cnf.digest),
            idempotency_key=f"worker:{stage}",
            worker_build_id="test-build",
            prior_result_digest=prior,
        )

    frozen = await handlers.freeze(command("freeze"))
    assert await handlers.freeze(command("freeze")) == frozen
    solved = await handlers.solve(command("solve"))
    verified = await handlers.verify(command("verify", solved.result_digest))
    finalized = await handlers.finalize(command("finalize", verified.result_digest))
    reconciled = await handlers.reconcile(command("reconcile", finalized.result_digest))
    assert reconciled.result_digest == finalized.result_digest
    replacement = LocalActivityHandlers(configuration)
    assert await replacement.solve(command("solve")) == solved
    for method, stage in (
        (handlers.verify, "verify-missing"),
        (handlers.finalize, "finalize-missing"),
        (handlers.reconcile, "reconcile-missing"),
    ):
        with pytest.raises(ValueError):
            await method(command(stage))


@pytest.mark.asyncio
async def test_activity_contract_dispatches_all_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[str] = []

    async def handler(command: ActivityCommand) -> ActivityResult:
        seen.append(command.idempotency_key)
        return ActivityResult(
            result_digest=str(Sha256Digest.from_bytes(command.idempotency_key.encode())),
            checkpoint=command.idempotency_key,
        )

    monkeypatch.setattr("amra.workflows.activities.activity.heartbeat", lambda _: None)
    names = (
        "freeze_and_reserve",
        "solve_cnf",
        "verify_and_record_evidence",
        "finalize_execution_manifest",
        "reconcile_cost",
    )
    activities = SatActivities(dict.fromkeys(names, handler))
    raw = ActivityCommand(
        obligation_id=str(uuid4()),
        cnf_digest=str(Sha256Digest.from_bytes(b"cnf")),
        idempotency_key="activity",
        worker_build_id="test",
    ).model_dump(mode="json")
    for operation in (
        activities.freeze_and_reserve,
        activities.solve_cnf,
        activities.verify_and_record_evidence,
        activities.finalize_execution_manifest,
        activities.reconcile_cost,
    ):
        assert (await operation(raw))["checkpoint"] == "activity"
    assert seen == ["activity"] * 5


def test_cli_control_and_reproduction_commands(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    configuration = settings(tmp_path)
    monkeypatch.setattr(cli, "_settings", lambda: configuration)
    source = tmp_path / "input.cnf"
    source.write_bytes((FIXTURES / "unsat.cnf").read_bytes())

    monkeypatch.setattr(sys, "argv", ["amra", "artifact", "put", str(source)])
    assert cli.main() == 0
    assert "sha256:" in capsys.readouterr().out

    responses: list[tuple[str, str]] = []

    def request(method: str, path: str, *, payload: dict[str, Any] | None = None) -> object:
        responses.append((method, path))
        return {"path": path, "payload": payload}

    monkeypatch.setattr(cli, "_request", request)
    packet = tmp_path / "packet.json"
    packet.write_text('{"objective":"fixture"}')
    for argv in (
        ["amra", "obligation", "create", str(packet)],
        ["amra", "obligation", "run", "00000000-0000-0000-0000-000000000001"],
        ["amra", "obligation", "show", "00000000-0000-0000-0000-000000000001"],
    ):
        monkeypatch.setattr(sys, "argv", argv)
        assert cli.main() == 0
        capsys.readouterr()
    assert [method for method, _ in responses] == ["POST", "POST", "GET"]

    monkeypatch.setattr(sys, "argv", ["amra", "demo", "trust-loop", str(source)])
    assert cli.main() == 0
    output = capsys.readouterr().out
    manifest = next(
        line.split(": ", 1)[1]
        for line in output.splitlines()
        if line.startswith("execution manifest")
    )
    monkeypatch.setattr(sys, "argv", ["amra", "reproduce", manifest])
    assert cli.main() == 0
    assert "reproduction checker report digest" in capsys.readouterr().out

    upgraded: list[str] = []
    monkeypatch.setattr(cli.command, "upgrade", lambda _config, revision: upgraded.append(revision))
    monkeypatch.setattr(sys, "argv", ["amra", "db", "migrate"])
    assert cli.main() == 0
    assert upgraded == ["head"]


def test_http_request_and_structured_logging(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        def raise_for_status(self) -> None:
            pass

        def json(self) -> dict[str, bool]:
            return {"ok": True}

    captured: dict[str, object] = {}

    def request(method: str, url: str, **kwargs: object) -> Response:
        captured.update(method=method, url=url, **kwargs)
        return Response()

    monkeypatch.setattr(cli.httpx, "request", request)
    assert cli._request("POST", "/v1/test", payload={"x": 1}) == {"ok": True}
    assert captured["method"] == "POST"

    record = logging.LogRecord("amra", logging.INFO, __file__, 1, "verified %s", ("CNF",), None)
    record.obligation_id = "obligation-1"
    payload = json.loads(JsonTraceFormatter().format(record))
    assert payload["message"] == "verified CNF"
    assert payload["obligation_id"] == "obligation-1"
    configure_json_logging(logging.DEBUG)
    assert logging.getLogger().level == logging.DEBUG


def test_scientific_subprocess_network_is_denied(tmp_path: Path) -> None:
    result = LocalProcessExecutor().execute(
        (
            sys.executable,
            "-c",
            "import socket; "
            "\ntry: socket.socket()"
            "\nexcept PermissionError: print('DENIED')"
            "\nelse: raise SystemExit(9)",
        ),
        cwd=tmp_path,
        limits=ResourceLimits(),
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == b"DENIED"
