# ADR-003: Hexagonal domain boundary

## Context

Scientific state must survive provider replacement and retain strict invariants.

## Decision

Use one `src/amra` package with immutable domain values, application transaction boundaries, typed Protocol ports, and provider-specific adapters. Pydantic v2 governs API and workflow payloads; frozen dataclasses govern the core.

## Alternatives considered

A framework-centered service compressed early code while coupling epistemic state to infrastructure. ORM entities as domain objects introduced identity-map semantics into append-oriented records.

## Material consequences

Adapters carry translation work and conformance tests. Domain code imports zero provider SDKs.

## Failure modes

Leaking boto3, SQLAlchemy, Temporal, FastAPI, or process details into the domain would erode portability.

## Reversal path

Ports can gain versioned capabilities; adapter replacement leaves domain serialization stable.

## Verification

Static import checks, strict Pyright, adapter tests, and repository review enforce the boundary.
