"""Local Phase 1 scientific trust-loop application service."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

from amra.adapters.artifacts.canonical import canonical_json_bytes
from amra.adapters.execution.dimacs import check_assignment, parse_dimacs
from amra.adapters.execution.sat import SatCertificatePipeline, SatExecutionResult, SatOutcome
from amra.domain.budget import Money
from amra.domain.identifiers import ObligationId, Sha256Digest
from amra.domain.obligation import Obligation, ObligationState
from amra.ports.artifacts import ArtifactPort
from amra.ports.clock import ClockPort
from amra.ports.costs import CostPort
from amra.ports.ledger import LedgerPort


@dataclass(frozen=True, slots=True)
class SyntheticPriceBook:
    version: str = "phase1-local-2026-08-12"
    solver_per_second: Decimal = Decimal("0.001000")
    verification_per_second: Decimal = Decimal("0.001000")
    minimum_charge: Decimal = Decimal("0.000001")

    def price(self, result: SatExecutionResult) -> Money:
        converter_seconds = 0.0 if result.converter is None else result.converter.wall_time_seconds
        seconds = Decimal(
            str(
                result.solver.wall_time_seconds
                + converter_seconds
                + result.validator.wall_time_seconds
            )
        )
        charge = max(self.minimum_charge, seconds * self.solver_per_second)
        return Money.usd(charge)


@dataclass(frozen=True, slots=True)
class TrustLoopOutcome:
    obligation_id: ObligationId
    cnf_digest: Sha256Digest
    result: SatOutcome
    evidence_digest: Sha256Digest
    checker_report_digest: Sha256Digest
    manifest_digest: Sha256Digest
    disposition: str
    reserved_cost: Money
    actual_cost: Money
    released_cost: Money


class TrustLoopService:
    """Freeze, execute, verify, account, and manifest one SAT obligation."""

    def __init__(
        self,
        artifacts: ArtifactPort,
        ledger: LedgerPort,
        costs: CostPort,
        clock: ClockPort,
        pipeline: SatCertificatePipeline,
        workspace_root: Path,
        price_book: SyntheticPriceBook | None = None,
    ) -> None:
        self._artifacts = artifacts
        self._ledger = ledger
        self._costs = costs
        self._clock = clock
        self._pipeline = pipeline
        self._workspace_root = workspace_root
        self._price_book = price_book or SyntheticPriceBook()
        self._workspace_root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def run(
        self,
        cnf_bytes: bytes,
        *,
        objective: str,
        idempotency_key: str,
        worst_case_cost: Money | None = None,
    ) -> TrustLoopOutcome:
        worst_case_cost = worst_case_cost or Money.usd("0.025000")
        parse_dimacs(cnf_bytes)
        cnf = self._artifacts.put_if_absent(
            cnf_bytes,
            media_type="application/x-dimacs-cnf",
            actor="amra:operator",
            retention_class="SCIENTIFIC_INPUT",
        )
        obligation = Obligation(
            id=ObligationId.new(),
            objective=objective,
            updated_at=self._clock.now(),
        )
        obligation = self._ledger.create_obligation(obligation, f"{idempotency_key}:create")
        packet_bytes = canonical_json_bytes(
            {
                "cnf_digest": str(cnf.digest),
                "identity_transform": "amra.transform.cnf-identity.v1",
                "objective": objective,
                "obligation_id": str(obligation.id),
                "policy_versions": {"budget": "0.1.0", "routing": "0.1.0"},
                "schema_version": "amra.phase1-sat-obligation.v1",
            }
        )
        packet = self._artifacts.put_if_absent(
            packet_bytes,
            media_type="application/vnd.amra.obligation+json",
            actor="amra:application",
            retention_class="LEDGER",
        )
        obligation = obligation.with_packet(packet.digest).transition(
            ObligationState.READY,
            expected_version=obligation.version,
            at=self._clock.now(),
        )
        obligation = self._ledger.compare_and_set_obligation(
            obligation,
            0,
            f"{idempotency_key}:freeze",
        )
        reservation = self._costs.reserve(
            "solver",
            worst_case_cost,
            f"{idempotency_key}:reserve",
        )
        reserved = obligation.transition(
            ObligationState.RESERVED,
            expected_version=obligation.version,
            at=self._clock.now(),
        )
        obligation = self._ledger.compare_and_set_obligation(
            reserved,
            obligation.version,
            f"{idempotency_key}:reserved",
        )
        running = obligation.transition(
            ObligationState.RUNNING,
            expected_version=obligation.version,
            at=self._clock.now(),
        )
        obligation = self._ledger.compare_and_set_obligation(
            running,
            obligation.version,
            f"{idempotency_key}:running",
        )

        workspace = Path(tempfile.mkdtemp(prefix=f"{obligation.id}-", dir=self._workspace_root))
        execution_workspace = workspace / "scientific-execution"
        result = self._pipeline.run(cnf_bytes, execution_workspace)
        output_records = self._store_execution_outputs(result)
        actual = self._price_book.price(result)
        reconciliation = self._costs.reconcile(
            reservation.idempotency_key,
            actual,
            f"{idempotency_key}:reconcile",
        )
        released = next(event.amount for event in reconciliation if event.state.value == "RELEASED")
        awaiting = obligation.transition(
            ObligationState.AWAITING_EVIDENCE,
            expected_version=obligation.version,
            at=self._clock.now(),
        )
        obligation = self._ledger.compare_and_set_obligation(
            awaiting,
            obligation.version,
            f"{idempotency_key}:evidence",
        )
        manifest_bytes = self._manifest_bytes(
            obligation,
            cnf.digest,
            packet.digest,
            result,
            output_records,
            reservation.amount,
            actual,
            released,
        )
        manifest = self._artifacts.put_if_absent(
            manifest_bytes,
            media_type="application/vnd.amra.execution-manifest+json",
            actor="amra:application",
            retention_class="PROMOTED_EVIDENCE",
        )
        succeeded = obligation.transition(
            ObligationState.SUCCEEDED,
            expected_version=obligation.version,
            at=self._clock.now(),
        )
        self._ledger.compare_and_set_obligation(
            succeeded,
            obligation.version,
            f"{idempotency_key}:succeeded",
        )
        if result.outcome is SatOutcome.SAT:
            evidence_digest = output_records["assignment"]
        else:
            evidence_digest = output_records["certificate"]
        return TrustLoopOutcome(
            obligation.id,
            cnf.digest,
            result.outcome,
            evidence_digest,
            output_records["checker_report"],
            manifest.digest,
            "ACCEPTED",
            reservation.amount,
            actual,
            released,
        )

    def _store_execution_outputs(
        self,
        result: SatExecutionResult,
    ) -> dict[str, Sha256Digest]:
        records: dict[str, Sha256Digest] = {}
        payloads: tuple[tuple[str, bytes | None, str, str], ...] = (
            ("solver_stdout", result.solver.stdout, "text/plain", "RAW_EXECUTION"),
            ("solver_stderr", result.solver.stderr, "text/plain", "RAW_EXECUTION"),
            (
                "converter_stdout",
                None if result.converter is None else result.converter.stdout,
                "text/plain",
                "RAW_EXECUTION",
            ),
            (
                "converter_stderr",
                None if result.converter is None else result.converter.stderr,
                "text/plain",
                "RAW_EXECUTION",
            ),
            ("assignment", result.assignment, "text/plain", "PROMOTED_EVIDENCE"),
            ("proof_trace", result.proof_trace, "application/x-drat", "RAW_EXECUTION"),
            ("certificate", result.certificate, "application/x-lrat", "PROMOTED_EVIDENCE"),
            (
                "checker_report",
                result.checker_report,
                "application/vnd.amra.checker-report+json",
                "PROMOTED_EVIDENCE",
            ),
        )
        for role, content, media_type, retention in payloads:
            if content is None:
                continue
            metadata = self._artifacts.put_if_absent(
                content,
                media_type=media_type,
                actor="amra:scientific-execution",
                retention_class=retention,
            )
            records[role] = metadata.digest
        return records

    def _manifest_bytes(
        self,
        obligation: Obligation,
        cnf_digest: Sha256Digest,
        packet_digest: Sha256Digest,
        result: SatExecutionResult,
        outputs: dict[str, Sha256Digest],
        reserved: Money,
        actual: Money,
        released: Money,
    ) -> bytes:
        toolchain = self._pipeline.toolchain
        converter_seconds = 0.0 if result.converter is None else result.converter.wall_time_seconds
        measures: dict[str, dict[str, str | None]] = {
            "advice_bits": {"reason": "FORMALLY_INAPPLICABLE", "unit": "bits", "value": None},
            "aggregate_parallel_work": {
                "reason": None,
                "unit": "process-seconds",
                "value": str(
                    result.solver.wall_time_seconds
                    + converter_seconds
                    + result.validator.wall_time_seconds
                ),
            },
            "algebraic_degree": {
                "reason": "FORMALLY_INAPPLICABLE",
                "unit": "degree",
                "value": None,
            },
            "communication_bytes": {"reason": None, "unit": "bytes", "value": "0"},
            "discovery_time": {"reason": None, "unit": "seconds", "value": "0"},
            "execution_time": {
                "reason": None,
                "unit": "seconds",
                "value": str(result.solver.wall_time_seconds),
            },
            "monetary_cost": {"reason": None, "unit": "USD", "value": str(actual.amount)},
            "peak_memory": {
                "reason": "TOOL_DID_NOT_REPORT"
                if result.solver.peak_memory_bytes is None
                else None,
                "unit": "bytes",
                "value": None
                if result.solver.peak_memory_bytes is None
                else str(result.solver.peak_memory_bytes),
            },
            "precision_bits": {"reason": "FORMALLY_INAPPLICABLE", "unit": "bits", "value": None},
            "random_bits": {"reason": None, "unit": "bits", "value": "0"},
            "rank": {"reason": "FORMALLY_INAPPLICABLE", "unit": "rank", "value": None},
            "verification_time": {
                "reason": None,
                "unit": "seconds",
                "value": str(converter_seconds + result.validator.wall_time_seconds),
            },
            "width": {"reason": "INSTRUMENT_UNAVAILABLE", "unit": "literals", "value": None},
        }
        tools = [
            {
                "executable_digest": str(pin.executable_digest()),
                "image_digest": pin.image_digest,
                "image_status": pin.image_status,
                "name": pin.name,
                "source_commit": pin.source_commit,
                "source_repository": pin.source_repository,
            }
            for pin in (toolchain.solver, toolchain.converter, toolchain.checker)
        ]
        processes = {
            "solver": self._process_manifest(result.solver),
            "validator": self._process_manifest(result.validator),
        }
        if result.converter is not None:
            processes["converter"] = self._process_manifest(result.converter)
        limits = self._pipeline.limits
        return canonical_json_bytes(
            {
                "attempt_id": str(obligation.id),
                "cost": {
                    "actual": str(actual.amount),
                    "currency": actual.currency,
                    "price_book_version": self._price_book.version,
                    "released": str(released.amount),
                    "reserved": str(reserved.amount),
                },
                "dirty_state": False,
                "environment": {"network_policy": "deny_all", "worker_build_id": "amra-phase1-v1"},
                "executions": processes,
                "identity_transform": {
                    "name": "cnf-identity",
                    "relation": "EQUIVALENCE",
                    "version": "1.0.0",
                },
                "input_artifacts": {
                    "cnf": str(cnf_digest),
                    "obligation_packet": str(packet_digest),
                },
                "nondeterminism": (
                    "wall-clock measurements only; solver semantics deterministic "
                    "for frozen input and tool pins"
                ),
                "obligation_id": str(obligation.id),
                "outputs": {name: str(digest) for name, digest in sorted(outputs.items())},
                "policy_versions": {"budget": "0.1.0", "routing": "0.1.0"},
                "repository": "https://github.com/Communist-Engineer/ARMA",
                "resource_limits": {
                    "cpu_seconds": limits.cpu_seconds,
                    "file_size_bytes": limits.file_size_bytes,
                    "memory_bytes": limits.memory_bytes,
                    "output_bytes": limits.output_bytes,
                    "process_count": limits.process_count,
                    "wall_seconds": limits.wall_seconds,
                },
                "resource_vector": measures,
                "result": result.outcome.value,
                "schema_version": "amra.execution-manifest.v1",
                "tools": tools,
            }
        )

    @staticmethod
    def _process_manifest(process: Any) -> dict[str, Any]:
        return {
            "argv": list(process.argv),
            "exit_code": process.exit_code,
            "peak_memory_bytes": process.peak_memory_bytes,
            "stderr_digest": str(Sha256Digest.from_bytes(process.stderr)),
            "stdout_digest": str(Sha256Digest.from_bytes(process.stdout)),
            "wall_time_seconds": str(process.wall_time_seconds),
        }

    def verify_manifest(self, manifest_digest: Sha256Digest) -> Sha256Digest:
        manifest_bytes = self._artifacts.read(manifest_digest)
        if Sha256Digest.from_bytes(manifest_bytes) != manifest_digest:
            raise ValueError("manifest digest verification failed")
        manifest: dict[str, Any] = json.loads(manifest_bytes)
        outputs: dict[str, str] = manifest["outputs"]
        cnf_digest = Sha256Digest(manifest["input_artifacts"]["cnf"])
        cnf = self._artifacts.read(cnf_digest)
        if manifest["result"] == "SAT":
            assignment = self._artifacts.read(Sha256Digest(outputs["assignment"]))
            report = canonical_json_bytes(check_assignment(cnf, assignment))
        else:
            certificate_digest = Sha256Digest(outputs["certificate"])
            certificate = self._artifacts.read(certificate_digest)
            with tempfile.TemporaryDirectory(dir=self._workspace_root) as directory:
                workspace = Path(directory)
                cnf_path = workspace / "input.cnf"
                certificate_path = workspace / "certificate.lrat"
                cnf_path.write_bytes(cnf)
                certificate_path.write_bytes(certificate)
                checked = self._pipeline.verify_certificate(cnf_path, certificate_path, workspace)
                report = canonical_json_bytes(
                    {
                        "accepted": checked.exit_code == 0
                        and b"s VERIFIED UNSAT" in checked.stdout,
                        "checker": self._pipeline.toolchain.checker.name,
                        "exit_code": checked.exit_code,
                        "schema_version": "amra.unsat-certificate-check.v1",
                        "stderr": checked.stderr.decode("utf-8", errors="replace"),
                        "stdout": checked.stdout.decode("utf-8", errors="replace"),
                    }
                )
        reproduction_report = canonical_json_bytes(
            {
                "checker_report": json.loads(report),
                "manifest_digest": str(manifest_digest),
                "schema_version": "amra.reproduction-check.v1",
            }
        )
        verified = self._artifacts.put_if_absent(
            reproduction_report,
            media_type="application/vnd.amra.checker-report+json",
            actor="amra:reproducer",
            retention_class="REPRODUCTION",
        )
        return verified.digest
