from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from amra.adapters.artifacts.local import LocalArtifactStore
from amra.adapters.clock import FixedClock
from amra.adapters.costs.memory import BudgetPolicy, InMemoryCostLedger
from amra.adapters.execution.process import LocalProcessExecutor
from amra.adapters.execution.sat import SatCertificatePipeline, SatToolchain
from amra.adapters.ledger.memory import InMemoryLedger
from amra.application.trust_loop import TrustLoopService
from amra.domain.budget import Money

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.mark.integration
@pytest.mark.parametrize("fixture", ["sat.cnf", "unsat.cnf"])
def test_clean_environment_reproduction(
    fixture: str,
    tmp_path: Path,
    toolchain: SatToolchain,
) -> None:
    clock = FixedClock(datetime(2026, 8, 12, tzinfo=UTC))
    store = LocalArtifactStore(tmp_path / "artifacts", clock)
    service = TrustLoopService(
        store,
        InMemoryLedger(),
        InMemoryCostLedger(
            BudgetPolicy(
                category_limits={"solver": Money.usd("1"), "verification": Money.usd("0")},
                protected_verification_reserve=Money.usd("0.1"),
            )
        ),
        clock,
        SatCertificatePipeline(LocalProcessExecutor(), toolchain),
        tmp_path / "workspaces",
    )
    content = (FIXTURES / fixture).read_bytes()
    outcome = service.run(content, objective="Reproduction fixture", idempotency_key=fixture)
    reproduced = service.verify_manifest(outcome.manifest_digest)
    assert store.verify(reproduced).retention_class == "REPRODUCTION"
