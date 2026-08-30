"""AMRA operator and reproducibility commands."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from alembic import command
from alembic.config import Config

from amra.adapters.artifacts.local import LocalArtifactStore
from amra.adapters.clock import SystemClock
from amra.adapters.costs.memory import BudgetPolicy, InMemoryCostLedger
from amra.adapters.execution.process import LocalProcessExecutor
from amra.adapters.execution.sat import SatCertificatePipeline, SatToolchain, ToolPin
from amra.adapters.ledger.memory import InMemoryLedger
from amra.application.trust_loop import TrustLoopService
from amra.config import Settings
from amra.domain.budget import Money
from amra.domain.identifiers import Sha256Digest

CADICAL_COMMIT = "c60730422e758ef1cebe7aeddf2dda31c996bf04"
DRAT_TRIM_COMMIT = "2e3b2dc0ecf938addbd779d42877b6ed69d9a985"
CAKE_LPR_COMMIT = "a36874a8b750b43fe4b385b8ddbf5b033e46a3fa"


def _settings() -> Settings:
    return Settings()


def _toolchain(settings: Settings) -> SatToolchain:
    lock_path = Path("config/toolchain.lock.json")
    images: dict[str, str | None] = {}
    statuses: dict[str, str] = {}
    if lock_path.is_file():
        lock = json.loads(lock_path.read_bytes())
        images = {tool["name"]: tool["image_digest"] for tool in lock["tools"]}
        statuses = {tool["name"]: tool["image_status"] for tool in lock["tools"]}
    return SatToolchain(
        solver=ToolPin(
            "cadical",
            settings.cadical_path.resolve(),
            CADICAL_COMMIT,
            "https://github.com/arminbiere/cadical",
            images.get("cadical", "local-build:unpublished"),
            statuses.get("cadical", "local build"),
        ),
        converter=ToolPin(
            "drat-trim",
            settings.drat_trim_path.resolve(),
            DRAT_TRIM_COMMIT,
            "https://github.com/marijnheule/drat-trim",
            images.get("drat-trim", "local-build:unpublished"),
            statuses.get("drat-trim", "local build"),
        ),
        checker=ToolPin(
            "cake_lpr",
            settings.cake_lpr_path.resolve(),
            CAKE_LPR_COMMIT,
            "https://github.com/tanyongkiam/cake_lpr",
            images.get("cake_lpr", "local-build:unpublished"),
            statuses.get("cake_lpr", "local build"),
        ),
    )


def _service(settings: Settings) -> TrustLoopService:
    clock = SystemClock()
    artifacts = LocalArtifactStore(settings.artifact_root, clock)
    costs = InMemoryCostLedger(
        BudgetPolicy(
            category_limits={
                "solver": Money.usd("25"),
                "verification": Money.usd("0"),
            },
            protected_verification_reserve=Money.usd("2"),
        )
    )
    return TrustLoopService(
        artifacts,
        InMemoryLedger(),
        costs,
        clock,
        SatCertificatePipeline(LocalProcessExecutor(), _toolchain(settings)),
        settings.workspace_root,
    )


def _request(method: str, path: str, *, payload: dict[str, Any] | None = None) -> Any:
    settings = _settings()
    headers = {"Idempotency-Key": str(uuid4())} if method != "GET" else {}
    response = httpx.request(
        method,
        f"{settings.api_url.rstrip('/')}{path}",
        json=payload,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="amra")
    groups = parser.add_subparsers(dest="group", required=True)

    database = groups.add_parser("db")
    database_actions = database.add_subparsers(dest="action", required=True)
    database_actions.add_parser("migrate")

    artifact = groups.add_parser("artifact")
    artifact_actions = artifact.add_subparsers(dest="action", required=True)
    put = artifact_actions.add_parser("put")
    put.add_argument("file", type=Path)
    put.add_argument("--media-type", default="application/octet-stream")

    obligation = groups.add_parser("obligation")
    obligation_actions = obligation.add_subparsers(dest="action", required=True)
    create = obligation_actions.add_parser("create")
    create.add_argument("packet", type=Path)
    run = obligation_actions.add_parser("run")
    run.add_argument("id")
    show = obligation_actions.add_parser("show")
    show.add_argument("id")

    demo = groups.add_parser("demo")
    demo_actions = demo.add_subparsers(dest="action", required=True)
    trust_loop = demo_actions.add_parser("trust-loop")
    trust_loop.add_argument("cnf", type=Path, nargs="?", default=Path("tests/fixtures/unsat.cnf"))

    reproduce = groups.add_parser("reproduce")
    reproduce.add_argument("manifest_digest")
    verify = groups.add_parser("verify")
    verify.add_argument("manifest_digest")
    return parser


def main() -> int:
    arguments = _parser().parse_args()
    settings = _settings()
    if arguments.group == "db":
        configuration = Config("alembic.ini")
        configuration.set_main_option("sqlalchemy.url", settings.database_url)
        command.upgrade(configuration, "head")
        return 0
    if arguments.group == "artifact":
        store = LocalArtifactStore(settings.artifact_root, SystemClock())
        metadata = store.put_if_absent(
            arguments.file.read_bytes(),
            media_type=arguments.media_type,
            actor=f"operator:{os.getuid()}",
        )
        print(metadata.digest)
        return 0
    if arguments.group == "obligation":
        if arguments.action == "create":
            payload = json.loads(arguments.packet.read_bytes())
            print(json.dumps(_request("POST", "/v1/obligations", payload=payload), indent=2))
        elif arguments.action == "run":
            print(json.dumps(_request("POST", f"/v1/obligations/{arguments.id}:start"), indent=2))
        else:
            print(json.dumps(_request("GET", f"/v1/obligations/{arguments.id}"), indent=2))
        return 0
    if arguments.group == "demo":
        outcome = _service(settings).run(
            arguments.cnf.read_bytes(),
            objective=f"Verify frozen CNF {arguments.cnf.name}",
            idempotency_key=f"demo:{Sha256Digest.from_bytes(arguments.cnf.read_bytes()).hex()}",
        )
        print(f"obligation ID: {outcome.obligation_id}")
        print(f"frozen CNF digest: {outcome.cnf_digest}")
        print(f"solver result: {outcome.result.value}")
        print(f"assignment or proof digest: {outcome.evidence_digest}")
        print(f"checker report digest: {outcome.checker_report_digest}")
        print(f"execution manifest digest: {outcome.manifest_digest}")
        print(f"final evidence disposition: {outcome.disposition}")
        print(f"synthetic reserved cost: {outcome.reserved_cost.amount} USD")
        print(f"synthetic actual cost: {outcome.actual_cost.amount} USD")
        print(f"synthetic released cost: {outcome.released_cost.amount} USD")
        print(f"synthetic reconciled cost: {outcome.actual_cost.amount} USD")
        print(f"reproduction command: amra reproduce {outcome.manifest_digest}")
        return 0
    manifest = Sha256Digest(arguments.manifest_digest)
    report = _service(settings).verify_manifest(manifest)
    print(f"verified manifest: {manifest}")
    print(f"reproduction checker report digest: {report}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
