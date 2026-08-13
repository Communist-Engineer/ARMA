"""Three-process CaDiCaL → DRAT-trim → cake_lpr scientific trust boundary."""

from __future__ import annotations

import hashlib
import json
import os
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from amra.adapters.artifacts.canonical import canonical_json_bytes
from amra.adapters.execution.dimacs import parse_dimacs
from amra.domain.errors import ExecutionFailure, InvalidCertificate
from amra.domain.identifiers import Sha256Digest
from amra.ports.execution import ExecutionPort, ProcessResult, ResourceLimits


class SatOutcome(StrEnum):
    SAT = "SAT"
    UNSAT = "UNSAT"


@dataclass(frozen=True, slots=True)
class ToolPin:
    name: str
    executable: Path
    source_commit: str
    source_repository: str
    image_digest: str | None
    image_status: str = "local-test-build"

    def executable_digest(self) -> Sha256Digest:
        return Sha256Digest.from_bytes(self.executable.read_bytes())


@dataclass(frozen=True, slots=True)
class SatToolchain:
    solver: ToolPin
    converter: ToolPin
    checker: ToolPin


@dataclass(frozen=True, slots=True)
class SatExecutionResult:
    outcome: SatOutcome
    solver: ProcessResult
    converter: ProcessResult | None
    validator: ProcessResult
    assignment: bytes | None
    proof_trace: bytes | None
    certificate: bytes | None
    checker_report: bytes


class SatCertificatePipeline:
    """Generate and independently verify evidence from frozen DIMACS bytes."""

    def __init__(
        self,
        execution: ExecutionPort,
        toolchain: SatToolchain,
        limits: ResourceLimits | None = None,
    ) -> None:
        self._execution = execution
        self._toolchain = toolchain
        self._limits = limits or ResourceLimits()

    @property
    def toolchain(self) -> SatToolchain:
        return self._toolchain

    @property
    def limits(self) -> ResourceLimits:
        return self._limits

    @staticmethod
    def _write_exact(path: Path, content: bytes) -> None:
        with path.open("xb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

    def run(self, frozen_cnf: bytes, workspace: Path) -> SatExecutionResult:
        parse_dimacs(frozen_cnf)
        workspace.mkdir(mode=0o700, parents=True, exist_ok=False)
        cnf_path = workspace / "input.cnf"
        proof_path = workspace / "solver.drat"
        assignment_path = workspace / "assignment.txt"
        checker_report_path = workspace / "assignment-check.json"
        lrat_path = workspace / "certificate.lrat"
        self._write_exact(cnf_path, frozen_cnf)
        solver = self._execution.execute(
            (str(self._toolchain.solver.executable), str(cnf_path), str(proof_path)),
            cwd=workspace,
            limits=self._limits,
        )
        if solver.exit_code == 10 and b"s SATISFIABLE" in solver.stdout:
            assignment = (
                b"\n".join(line for line in solver.stdout.splitlines() if line.startswith(b"v "))
                + b"\n"
            )
            self._write_exact(assignment_path, assignment)
            package_root = str(Path(__file__).resolve().parents[3])
            validator = self._execution.execute(
                (
                    sys.executable,
                    "-m",
                    "amra.adapters.execution.assignment_checker_cli",
                    str(cnf_path),
                    str(assignment_path),
                    str(checker_report_path),
                ),
                cwd=workspace,
                limits=self._limits,
                environment={"PYTHONPATH": package_root},
            )
            report = checker_report_path.read_bytes()
            if validator.exit_code != 0 or not bool(json.loads(report)["accepted"]):
                raise InvalidCertificate("solver assignment failed independent validation")
            return SatExecutionResult(
                SatOutcome.SAT,
                solver,
                None,
                validator,
                assignment,
                None,
                None,
                report,
            )
        if solver.exit_code != 20 or b"s UNSATISFIABLE" not in solver.stdout:
            detail = solver.stderr.decode(errors="replace")
            raise ExecutionFailure(f"solver contract failed with exit {solver.exit_code}: {detail}")
        proof = proof_path.read_bytes()
        converter = self._execution.execute(
            (
                str(self._toolchain.converter.executable),
                str(cnf_path),
                str(proof_path),
                "-L",
                str(lrat_path),
            ),
            cwd=workspace,
            limits=self._limits,
        )
        if converter.exit_code != 0 or b"s VERIFIED" not in converter.stdout:
            raise InvalidCertificate("DRAT conversion/validation failed")
        certificate = lrat_path.read_bytes()
        checker = self.verify_certificate(cnf_path, lrat_path, workspace)
        report = canonical_json_bytes(
            {
                "accepted": checker.exit_code == 0 and b"s VERIFIED UNSAT" in checker.stdout,
                "checker": self._toolchain.checker.name,
                "exit_code": checker.exit_code,
                "schema_version": "amra.unsat-certificate-check.v1",
                "stderr": checker.stderr.decode("utf-8", errors="replace"),
                "stdout": checker.stdout.decode("utf-8", errors="replace"),
            }
        )
        if checker.exit_code != 0 or b"s VERIFIED UNSAT" not in checker.stdout:
            raise InvalidCertificate("cake_lpr rejected the generated certificate")
        return SatExecutionResult(
            SatOutcome.UNSAT,
            solver,
            converter,
            checker,
            None,
            proof,
            certificate,
            report,
        )

    def verify_certificate(
        self,
        cnf_path: Path,
        certificate_path: Path,
        workspace: Path,
    ) -> ProcessResult:
        return self._execution.execute(
            (
                str(self._toolchain.checker.executable),
                "--CML_HEAP_SIZE=128",
                "--CML_STACK_SIZE=128",
                str(cnf_path),
                str(certificate_path),
            ),
            cwd=workspace,
            limits=self._limits,
        )


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
