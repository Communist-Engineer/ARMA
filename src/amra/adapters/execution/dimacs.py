"""Strict DIMACS parsing and independent SAT assignment checking."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from amra.domain.errors import InvalidAssignment, InvalidDimacs


@dataclass(frozen=True, slots=True)
class DimacsCnf:
    variable_count: int
    clauses: tuple[tuple[int, ...], ...]


def parse_dimacs(content: bytes) -> DimacsCnf:
    """Parse ASCII DIMACS with exact header, count, range, and terminator checks."""

    try:
        text = content.decode("ascii")
    except UnicodeDecodeError as error:
        raise InvalidDimacs("DIMACS input must be ASCII") from error

    header: tuple[int, int] | None = None
    clauses: list[tuple[int, ...]] = []
    pending: list[int] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("c"):
            continue
        if stripped.startswith("p"):
            if header is not None:
                raise InvalidDimacs(f"line {line_number}: duplicate DIMACS header")
            parts = stripped.split()
            if len(parts) != 4 or parts[:2] != ["p", "cnf"]:
                raise InvalidDimacs(f"line {line_number}: expected 'p cnf <vars> <clauses>'")
            try:
                variable_count, clause_count = int(parts[2]), int(parts[3])
            except ValueError as error:
                raise InvalidDimacs(
                    f"line {line_number}: header counts must be integers"
                ) from error
            if variable_count < 0 or clause_count < 0:
                raise InvalidDimacs(f"line {line_number}: header counts must be nonnegative")
            header = variable_count, clause_count
            continue
        if header is None:
            raise InvalidDimacs(f"line {line_number}: clause appears before the header")
        for token in stripped.split():
            try:
                literal = int(token)
            except ValueError as error:
                raise InvalidDimacs(
                    f"line {line_number}: literal {token!r} is not an integer"
                ) from error
            if literal == 0:
                clauses.append(tuple(pending))
                pending.clear()
                continue
            if abs(literal) > header[0]:
                raise InvalidDimacs(
                    f"line {line_number}: literal {literal} exceeds variable range 1..{header[0]}"
                )
            pending.append(literal)

    if header is None:
        raise InvalidDimacs("DIMACS header is missing")
    if pending:
        raise InvalidDimacs("final clause lacks a zero terminator")
    if len(clauses) != header[1]:
        raise InvalidDimacs(
            f"header declares {header[1]} clauses while input contains {len(clauses)}"
        )
    return DimacsCnf(header[0], tuple(clauses))


def parse_assignment(content: bytes, variable_count: int) -> dict[int, bool]:
    """Parse solver `v` lines; Phase 1 rejects every partial assignment."""

    try:
        text = content.decode("ascii")
    except UnicodeDecodeError as error:
        raise InvalidAssignment("assignment output must be ASCII") from error
    literals: list[int] = []
    terminated = False
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith(("c", "s")):
            continue
        tokens = stripped.split()
        if tokens[0] == "v":
            tokens = tokens[1:]
        for token in tokens:
            try:
                literal = int(token)
            except ValueError as error:
                raise InvalidAssignment(
                    f"line {line_number}: assignment token {token!r} is invalid"
                ) from error
            if literal == 0:
                terminated = True
                continue
            if terminated:
                raise InvalidAssignment("assignment contains literals after its zero terminator")
            if abs(literal) < 1 or abs(literal) > variable_count:
                raise InvalidAssignment(
                    f"assignment literal {literal} exceeds variable range 1..{variable_count}"
                )
            literals.append(literal)
    if not terminated:
        raise InvalidAssignment("assignment lacks a zero terminator")
    assignment: dict[int, bool] = {}
    for literal in literals:
        variable = abs(literal)
        value = literal > 0
        previous = assignment.get(variable)
        if previous is not None and previous != value:
            raise InvalidAssignment(f"variable {variable} receives contradictory values")
        if previous is not None:
            raise InvalidAssignment(f"variable {variable} appears more than once")
        assignment[variable] = value
    expected = set(range(1, variable_count + 1))
    missing = sorted(expected - assignment.keys())
    if missing:
        raise InvalidAssignment(
            "partial assignments are rejected; missing variables: " + ",".join(map(str, missing))
        )
    return assignment


def check_assignment(cnf_content: bytes, assignment_content: bytes) -> dict[str, Any]:
    cnf = parse_dimacs(cnf_content)
    assignment = parse_assignment(assignment_content, cnf.variable_count)
    clause_results = [
        any(assignment[abs(literal)] is (literal > 0) for literal in clause)
        for clause in cnf.clauses
    ]
    failing = [index for index, accepted in enumerate(clause_results, start=1) if not accepted]
    return {
        "accepted": not failing,
        "assignment_policy": "TOTAL_EXACTLY_ONCE",
        "checked_clause_count": len(cnf.clauses),
        "clause_results": clause_results,
        "failing_clause_indices": failing,
        "schema_version": "amra.sat-assignment-check.v1",
        "variable_count": cnf.variable_count,
    }
