from __future__ import annotations

import itertools

import pytest
from hypothesis import given
from hypothesis import strategies as st

from amra.adapters.execution.dimacs import check_assignment, parse_assignment, parse_dimacs
from amra.domain.errors import InvalidAssignment, InvalidDimacs


def test_strict_dimacs_and_assignment_contracts() -> None:
    cnf = parse_dimacs(b"c comment\np cnf 2 2\n1\n-2 0\n2 0\n")
    assert cnf.variable_count == 2
    assert cnf.clauses == ((1, -2), (2,))
    assert check_assignment(b"p cnf 2 1\n1 2 0\n", b"v 1 -2 0\n")["accepted"]
    with pytest.raises(InvalidAssignment, match="partial assignments"):
        parse_assignment(b"v 1 0\n", 2)
    with pytest.raises(InvalidAssignment, match="contradictory"):
        parse_assignment(b"v 1 -1 0\n", 1)
    with pytest.raises(InvalidAssignment, match="more than once"):
        parse_assignment(b"v 1 1 0\n", 1)
    with pytest.raises(InvalidAssignment, match="terminator"):
        parse_assignment(b"v 1\n", 1)


@pytest.mark.parametrize(
    "content",
    [
        b"1 0\n",
        b"p cnf 1 2\n1 0\n",
        b"p cnf 1 1\n2 0\n",
        b"p cnf 1 1\n1\n",
        b"p cnf x 1\n1 0\n",
        b"p cnf 1 1\nword 0\n",
        b"p cnf 1 0\np cnf 1 0\n",
        "p cnf 1 0\nλ".encode(),
    ],
)
def test_invalid_dimacs_is_rejected(content: bytes) -> None:
    with pytest.raises(InvalidDimacs):
        parse_dimacs(content)


@st.composite
def formulas(draw: st.DrawFn) -> tuple[int, list[list[int]]]:
    variables = draw(st.integers(min_value=1, max_value=5))
    literal = st.integers(min_value=1, max_value=variables).flatmap(
        lambda value: st.sampled_from([value, -value])
    )
    clauses = draw(st.lists(st.lists(literal, min_size=0, max_size=5), min_size=0, max_size=8))
    return variables, clauses


@given(formulas())
def test_assignment_checker_matches_brute_force(
    formula: tuple[int, list[list[int]]],
) -> None:
    variables, clauses = formula
    lines = [f"p cnf {variables} {len(clauses)}"]
    lines.extend(" ".join([*(str(literal) for literal in clause), "0"]) for clause in clauses)
    cnf_bytes = ("\n".join(lines) + "\n").encode()
    for values in itertools.product([False, True], repeat=variables):
        assignment = (
            "v "
            + " ".join(
                str(index if value else -index) for index, value in enumerate(values, start=1)
            )
            + " 0\n"
        )
        report = check_assignment(cnf_bytes, assignment.encode())
        brute = all(
            any(values[abs(literal) - 1] is (literal > 0) for literal in clause)
            for clause in clauses
        )
        assert report["accepted"] is brute
