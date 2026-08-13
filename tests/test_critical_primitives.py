from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pytest

from amra.adapters.costs.memory import BudgetPolicy, InMemoryCostLedger
from amra.adapters.execution import assignment_checker_cli
from amra.adapters.execution.dimacs import parse_assignment, parse_dimacs
from amra.adapters.ledger.memory import InMemoryLedger
from amra.domain.budget import CostEvent, CostState, Money
from amra.domain.errors import (
    DuplicateIdempotencyConflict,
    InvalidAssignment,
    InvalidDimacs,
    InvalidTransition,
    InvariantViolation,
)
from amra.domain.identifiers import ObligationId, Sha256Digest
from amra.domain.obligation import Obligation, ObligationState


def test_money_and_cost_event_reject_every_malformed_boundary() -> None:
    with pytest.raises(InvariantViolation):
        Money.usd("-0.000001")
    with pytest.raises(InvariantViolation):
        Money.usd("1").__class__(Money.usd("1").amount, "usd")
    with pytest.raises(InvariantViolation):
        CostEvent(CostState.RESERVED, Money.usd("1"), "", "key")
    with pytest.raises(InvariantViolation):
        CostEvent(CostState.RESERVED, Money.usd("1"), "solver", "")


def test_budget_category_currency_and_idempotency_guards() -> None:
    ledger = InMemoryCostLedger(
        BudgetPolicy(
            {"solver": Money.usd("1")},
            protected_verification_reserve=Money.usd("0"),
        )
    )
    with pytest.raises(InvariantViolation, match="undefined"):
        ledger.reserve("unknown", Money.usd("1"), "unknown")
    with pytest.raises(InvariantViolation, match="currency"):
        ledger.reserve("solver", Money(Money.usd("1").amount, "EUR"), "currency")
    first = ledger.reserve("solver", Money.usd("0.5"), "same")
    assert ledger.reserve("solver", Money.usd("0.5"), "same") == first
    with pytest.raises(DuplicateIdempotencyConflict):
        ledger.reserve("solver", Money.usd("0.4"), "same")
    with pytest.raises(InvariantViolation, match="currenc"):
        ledger.reconcile("same", Money(Money.usd("0.1").amount, "EUR"), "actual")


def test_obligation_invariants_and_packet_freezing_guards() -> None:
    with pytest.raises(InvariantViolation):
        Obligation(ObligationId.new(), " ")
    with pytest.raises(InvariantViolation):
        Obligation(ObligationId.new(), "objective", version=-1)
    with pytest.raises(InvariantViolation):
        Obligation(ObligationId.new(), "objective", updated_at=datetime(2026, 1, 1))
    draft = Obligation(ObligationId.new(), "objective")
    with pytest.raises(InvariantViolation):
        draft.transition(
            ObligationState.READY,
            expected_version=0,
            at=datetime(2026, 1, 1),
        )
    ready = draft.transition(
        ObligationState.READY,
        expected_version=0,
        at=draft.updated_at,
    )
    with pytest.raises(InvalidTransition):
        ready.with_packet(Sha256Digest.from_bytes(b"packet"))


def test_memory_ledger_duplicate_identity_replay_and_stale_version() -> None:
    ledger = InMemoryLedger()
    draft = Obligation(ObligationId.new(), "objective")
    assert ledger.create_obligation(draft, "create") == draft
    assert ledger.create_obligation(draft, "create") == draft
    with pytest.raises(DuplicateIdempotencyConflict):
        ledger.create_obligation(draft, "conflicting-create")
    assert ledger.get_obligation(str(draft.id)) == draft
    ready = draft.transition(ObligationState.READY, expected_version=0, at=draft.updated_at)
    assert ledger.compare_and_set_obligation(ready, 0, "ready") == ready
    assert ledger.compare_and_set_obligation(ready, 0, "ready") == ready
    reserved = ready.transition(ObligationState.RESERVED, expected_version=1, at=ready.updated_at)
    with pytest.raises(InvalidTransition):
        ledger.compare_and_set_obligation(reserved, 0, "stale")


@pytest.mark.parametrize(
    "content",
    [
        b"p cnf 1\n",
        b"p cnf -1 0\n",
        b"c only\n",
    ],
)
def test_remaining_dimacs_header_failures(content: bytes) -> None:
    with pytest.raises(InvalidDimacs):
        parse_dimacs(content)


@pytest.mark.parametrize(
    "content",
    [
        "v 1 0\nλ".encode(),
        b"v word 0\n",
        b"v 1 0 -1\n",
        b"v 2 0\n",
    ],
)
def test_remaining_assignment_syntax_failures(content: bytes) -> None:
    with pytest.raises(InvalidAssignment):
        parse_assignment(content, 1)
    assert parse_assignment(b"c comment\ns SATISFIABLE\n1 0\n", 1) == {1: True}


def test_assignment_checker_process_entrypoint_reports_acceptance_and_rejection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cnf = tmp_path / "input.cnf"
    assignment = tmp_path / "assignment.txt"
    report = tmp_path / "report.json"
    cnf.write_bytes(b"p cnf 1 1\n1 0\n")
    assignment.write_bytes(b"v 1 0\n")
    monkeypatch.setattr(sys, "argv", ["checker", str(cnf), str(assignment), str(report)])
    assert assignment_checker_cli.main() == 0
    assert json.loads(report.read_bytes())["accepted"] is True
    assignment.write_bytes(b"v -1 0\n")
    assert assignment_checker_cli.main() == 2
    assert json.loads(report.read_bytes())["accepted"] is False
    assignment.write_bytes(b"v invalid 0\n")
    assert assignment_checker_cli.main() == 2
    assert "invalid" in json.loads(report.read_bytes())["error"]
