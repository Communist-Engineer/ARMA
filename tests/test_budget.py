from __future__ import annotations

import pytest

from amra.adapters.costs.memory import BudgetPolicy, InMemoryCostLedger
from amra.domain.budget import CostState, Money
from amra.domain.errors import BudgetExhausted, DuplicateIdempotencyConflict


def ledger() -> InMemoryCostLedger:
    return InMemoryCostLedger(
        BudgetPolicy(
            category_limits={
                "solver": Money.usd("1.000000"),
                "verification": Money.usd("0.000000"),
            },
            protected_verification_reserve=Money.usd("0.100000"),
        )
    )


@pytest.mark.parametrize(
    ("amount", "accepted"),
    [("0.999999", True), ("1.000000", True), ("1.000001", False)],
)
def test_reservation_boundaries(amount: str, accepted: bool) -> None:
    costs = ledger()
    if accepted:
        assert costs.reserve("solver", Money.usd(amount), "reserve").state is CostState.RESERVED
    else:
        with pytest.raises(BudgetExhausted):
            costs.reserve("solver", Money.usd(amount), "reserve")


def test_reconciliation_is_append_only_and_idempotent() -> None:
    costs = ledger()
    reservation = costs.reserve("solver", Money.usd("1"), "reserve")
    events = costs.reconcile(reservation.idempotency_key, Money.usd("0.4"), "reconcile")
    assert [event.state for event in events] == [
        CostState.DEBITED,
        CostState.RELEASED,
        CostState.RECONCILED,
    ]
    assert events[1].amount == Money.usd("0.6")
    assert costs.reconcile("reserve", Money.usd("0.4"), "reconcile") == events
    with pytest.raises(DuplicateIdempotencyConflict):
        costs.reconcile("reserve", Money.usd("0.5"), "reconcile")


def test_cancellation_releases_full_reservation_and_verification_reserve_survives() -> None:
    costs = ledger()
    solver = costs.reserve("solver", Money.usd("1"), "solver")
    cancellation = costs.reconcile(solver.idempotency_key, Money.usd("0"), "cancel")
    assert cancellation[1].amount == Money.usd("1")
    verification = costs.reserve("verification", Money.usd("0.1"), "verify")
    assert verification.amount == Money.usd("0.1")


def test_unattributed_actual_cost_is_quarantined() -> None:
    event = ledger().reconcile("missing", Money.usd("0.01"), "quarantine")[0]
    assert event.state is CostState.QUARANTINED
    assert event.reason_code == "RESERVATION_NOT_FOUND"
