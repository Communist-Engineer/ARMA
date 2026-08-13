# ADR-008: Pareto resource accounting

## Context

A scalar can conceal cost transfers among discovery, time, space, proof width, precision, advice, and parallel work.

## Decision

Record every specified coordinate plus explicit extras. Null always carries `FORMALLY_INAPPLICABLE`, `INSTRUMENT_UNAVAILABLE`, or `TOOL_DID_NOT_REPORT`; zero means measured zero. Canonical comparison uses strict Pareto dominance across matching measured units. Phase 1 registers the CNF identity transform.

## Alternatives considered

One weighted score simplified ranking while embedding political and scientific priorities in hidden weights. Lexicographic order privileged an arbitrary coordinate.

## Material consequences

Vectors with missing or mismatched coordinates remain incomparable. A scalar view must carry name, version, units, normalization, and weights.

## Failure modes

Silent nulls, unit mismatch, hidden parallel work, or excluded discovery effort can create false improvements.

## Reversal path

Add versioned coordinates and comparison policies while retaining raw vectors.

## Verification

Domain tests cover strict dominance, equality, unit/missing invariants, and manifest completeness.
