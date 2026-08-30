from __future__ import annotations

import json
from pathlib import Path

import pytest

from amra.adapters.execution.process import LocalProcessExecutor
from amra.adapters.execution.sat import SatCertificatePipeline, SatOutcome, SatToolchain

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.integration
def test_sat_assignment_receives_independent_process_validation(
    tmp_path: Path,
    toolchain: SatToolchain,
) -> None:
    pipeline = SatCertificatePipeline(LocalProcessExecutor(), toolchain)
    result = pipeline.run((FIXTURES / "sat.cnf").read_bytes(), tmp_path / "sat-run")
    assert result.outcome is SatOutcome.SAT
    assert result.assignment is not None
    assert json.loads(result.checker_report)["accepted"] is True
    assert "assignment_checker_cli" in " ".join(result.validator.argv)


@pytest.mark.integration
def test_unsat_certificate_accepts_valid_and_rejects_invalid(
    tmp_path: Path,
    toolchain: SatToolchain,
) -> None:
    pipeline = SatCertificatePipeline(LocalProcessExecutor(), toolchain)
    result = pipeline.run((FIXTURES / "unsat.cnf").read_bytes(), tmp_path / "unsat-run")
    assert result.outcome is SatOutcome.UNSAT
    assert result.proof_trace
    assert result.certificate
    assert json.loads(result.checker_report)["accepted"] is True

    valid = pipeline.verify_certificate(
        FIXTURES / "unsat.cnf",
        FIXTURES / "unsat-valid.lrat",
        tmp_path,
    )
    invalid = pipeline.verify_certificate(
        FIXTURES / "unsat.cnf",
        FIXTURES / "invalid.lrat",
        tmp_path,
    )
    assert valid.exit_code == 0 and b"s VERIFIED UNSAT" in valid.stdout
    assert invalid.exit_code != 0 or b"s VERIFIED UNSAT" not in invalid.stdout
