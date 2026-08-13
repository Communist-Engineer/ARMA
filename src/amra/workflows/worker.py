"""Local durable worker wiring for the Phase 1 trust loop."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import tempfile
from pathlib import Path

from temporalio.client import Client
from temporalio.worker import Worker

from amra.adapters.artifacts.canonical import canonical_json_bytes
from amra.adapters.artifacts.local import LocalArtifactStore
from amra.adapters.clock import SystemClock
from amra.adapters.execution.process import LocalProcessExecutor
from amra.adapters.execution.sat import SatCertificatePipeline, SatToolchain, ToolPin
from amra.config import Settings
from amra.domain.identifiers import Sha256Digest
from amra.workflows.activities import SatActivities
from amra.workflows.models import ActivityCommand, ActivityResult
from amra.workflows.sat_verification import SatVerificationWorkflow


class LocalActivityHandlers:
    """Persist activity results before acknowledgment so replacement workers reuse them."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.store = LocalArtifactStore(settings.artifact_root, SystemClock())
        self.journal = settings.artifact_root.parent / "activity-journal"
        self.journal.mkdir(mode=0o700, parents=True, exist_ok=True)
        self.pipeline = SatCertificatePipeline(
            LocalProcessExecutor(),
            SatToolchain(
                ToolPin(
                    "cadical",
                    settings.cadical_path,
                    "c60730422e758ef1cebe7aeddf2dda31c996bf04",
                    "https://github.com/arminbiere/cadical",
                    "local-worker-build",
                    "source-pinned worker executable",
                ),
                ToolPin(
                    "drat-trim",
                    settings.drat_trim_path,
                    "2e3b2dc0ecf938addbd779d42877b6ed69d9a985",
                    "https://github.com/marijnheule/drat-trim",
                    "local-worker-build",
                    "source-pinned worker executable",
                ),
                ToolPin(
                    "cake_lpr",
                    settings.cake_lpr_path,
                    "a36874a8b750b43fe4b385b8ddbf5b033e46a3fa",
                    "https://github.com/tanyongkiam/cake_lpr",
                    "local-worker-build",
                    "source-pinned worker executable",
                ),
            ),
        )

    def _journal_path(self, key: str) -> Path:
        return self.journal / f"{hashlib.sha256(key.encode()).hexdigest()}.json"

    async def _idempotent(self, command: ActivityCommand, operation: str) -> ActivityResult:
        path = self._journal_path(command.idempotency_key)
        if path.is_file():
            return ActivityResult.model_validate_json(path.read_bytes())
        result = await getattr(self, f"_{operation}")(command)
        temporary = path.with_suffix(f".{os.getpid()}.tmp")
        with temporary.open("xb") as stream:
            stream.write(canonical_json_bytes(result.model_dump(mode="json")))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        descriptor = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return result

    async def freeze(self, command: ActivityCommand) -> ActivityResult:
        return await self._idempotent(command, "freeze")

    async def _freeze(self, command: ActivityCommand) -> ActivityResult:
        self.store.read(Sha256Digest(command.cnf_digest))
        record = self.store.put_if_absent(
            canonical_json_bytes(
                {
                    "cnf_digest": command.cnf_digest,
                    "idempotency_key": command.idempotency_key,
                    "reserved_cost": "0.025000",
                    "schema_version": "amra.local-reservation.v1",
                }
            ),
            media_type="application/vnd.amra.reservation+json",
            actor="amra:worker",
            retention_class="LEDGER",
        )
        return ActivityResult(result_digest=str(record.digest), checkpoint="reserved")

    async def solve(self, command: ActivityCommand) -> ActivityResult:
        return await self._idempotent(command, "solve")

    async def _solve(self, command: ActivityCommand) -> ActivityResult:
        cnf = self.store.read(Sha256Digest(command.cnf_digest))
        workspace = Path(
            tempfile.mkdtemp(prefix="temporal-solver-", dir=self.settings.workspace_root)
        )
        result = self.pipeline.run(cnf, workspace / "execution")
        outputs: dict[str, str] = {}
        for name, content, media_type in (
            ("assignment", result.assignment, "text/plain"),
            ("proof_trace", result.proof_trace, "application/x-drat"),
            ("certificate", result.certificate, "application/x-lrat"),
            ("checker_report", result.checker_report, "application/vnd.amra.checker-report+json"),
            ("solver_stdout", result.solver.stdout, "text/plain"),
            ("solver_stderr", result.solver.stderr, "text/plain"),
        ):
            if content is not None:
                outputs[name] = str(
                    self.store.put_if_absent(
                        content,
                        media_type=media_type,
                        actor="amra:worker",
                        retention_class="SCIENTIFIC_EVIDENCE",
                    ).digest
                )
        envelope = self.store.put_if_absent(
            canonical_json_bytes(
                {
                    "actual_cost": "0.000001",
                    "cnf_digest": command.cnf_digest,
                    "outcome": result.outcome.value,
                    "outputs": outputs,
                    "schema_version": "amra.local-solver-envelope.v1",
                    "worker_build_id": command.worker_build_id,
                }
            ),
            media_type="application/vnd.amra.solver-envelope+json",
            actor="amra:worker",
            retention_class="LEDGER",
        )
        return ActivityResult(
            result_digest=str(envelope.digest), checkpoint="solver-output-durable"
        )

    async def verify(self, command: ActivityCommand) -> ActivityResult:
        return await self._idempotent(command, "verify")

    async def _verify(self, command: ActivityCommand) -> ActivityResult:
        if command.prior_result_digest is None:
            raise ValueError("verification requires the solver envelope")
        envelope = json.loads(self.store.read(Sha256Digest(command.prior_result_digest)))
        report_digest = Sha256Digest(envelope["outputs"]["checker_report"])
        report = json.loads(self.store.read(report_digest))
        if report.get("accepted") is not True:
            raise ValueError("immutable checker report rejects scientific evidence")
        return ActivityResult(
            result_digest=command.prior_result_digest,
            checkpoint="evidence-accepted",
        )

    async def finalize(self, command: ActivityCommand) -> ActivityResult:
        return await self._idempotent(command, "finalize")

    async def _finalize(self, command: ActivityCommand) -> ActivityResult:
        if command.prior_result_digest is None:
            raise ValueError("manifest finalization requires verified evidence")
        manifest = self.store.put_if_absent(
            canonical_json_bytes(
                {
                    "cnf_digest": command.cnf_digest,
                    "evidence_envelope_digest": command.prior_result_digest,
                    "network_policy": "deny_all",
                    "obligation_id": command.obligation_id,
                    "schema_version": "amra.temporal-execution-manifest.v1",
                    "worker_build_id": command.worker_build_id,
                }
            ),
            media_type="application/vnd.amra.execution-manifest+json",
            actor="amra:worker",
            retention_class="PROMOTED_EVIDENCE",
        )
        return ActivityResult(result_digest=str(manifest.digest), checkpoint="manifest-durable")

    async def reconcile(self, command: ActivityCommand) -> ActivityResult:
        return await self._idempotent(command, "reconcile")

    async def _reconcile(self, command: ActivityCommand) -> ActivityResult:
        if command.prior_result_digest is None:
            raise ValueError("cost reconciliation requires a manifest")
        self.store.put_if_absent(
            canonical_json_bytes(
                {
                    "actual": "0.000001",
                    "manifest_digest": command.prior_result_digest,
                    "released": "0.024999",
                    "reserved": "0.025000",
                    "schema_version": "amra.local-cost-reconciliation.v1",
                }
            ),
            media_type="application/vnd.amra.cost-reconciliation+json",
            actor="amra:worker",
            retention_class="LEDGER",
        )
        return ActivityResult(
            result_digest=command.prior_result_digest,
            checkpoint="cost-reconciled",
        )


async def run_worker() -> None:
    settings = Settings()
    settings.workspace_root.mkdir(mode=0o700, parents=True, exist_ok=True)
    handlers = LocalActivityHandlers(settings)
    activities = SatActivities(
        {
            "freeze_and_reserve": handlers.freeze,
            "solve_cnf": handlers.solve,
            "verify_and_record_evidence": handlers.verify,
            "finalize_execution_manifest": handlers.finalize,
            "reconcile_cost": handlers.reconcile,
        }
    )
    client = await Client.connect(settings.temporal_address)
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[SatVerificationWorkflow],
        activities=[
            activities.freeze_and_reserve,
            activities.solve_cnf,
            activities.verify_and_record_evidence,
            activities.finalize_execution_manifest,
            activities.reconcile_cost,
        ],
        build_id=settings.worker_build_id,
        use_worker_versioning=True,
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(run_worker())
