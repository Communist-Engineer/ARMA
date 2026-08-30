# ADR-009: Migration checksums and append-only events

## Context

`001_initial.sql` is a reviewed historical artifact whose exact bytes must remain stable while Alembic coordinates transactions.

## Decision

Alembic revisions hash each numbered SQL source. The baseline expects `1b9c85…`, removes only exact outer `BEGIN;` and `COMMIT;` bytes in memory, takes a PostgreSQL advisory transaction lock, and executes the preserved body. Later changes use numbered SQL plus new revisions. Cost, promotion, and idempotency records are append-only; corrections use compensating events.

## Alternatives considered

Copying the schema into Python invited drift. Editing the baseline erased reviewed provenance. Mutable reconciliation simplified queries while weakening auditability.

## Material consequences

Whitespace changes to a reviewed migration fail before execution. Downgrades use forward recovery.

## Failure modes

Checksum mismatch, altered wrapper bytes, parallel migrators, or event mutation produce explicit failures.

## Reversal path

Create a forward successor migration and compensating data events.

## Verification

Digest tests, fresh PostgreSQL apply, advisory locking, schema assertions, and append-only trigger tests verify the contract.
