# ADR-004: PostgreSQL 18 authoritative ledger

## Context

Obligations, idempotency, evidence dispositions, and cost events require transactional authority; vectors serve discovery only.

## Decision

Target PostgreSQL 18.4 plus pgvector 0.8.6. Use SQLAlchemy 2 Core and psycopg 3. PostgreSQL owns identities, relationships, compare-and-set state, reservations, and append-only events. Artifact storage owns bytes.

## Alternatives considered

SQLite simplified the demo but diverged on concurrency and extension behavior. An ORM identity map obscured explicit transaction boundaries.

## Material consequences

Local integration needs PostgreSQL and pgvector. Startup validates server and extension versions.

## Failure modes

Database/object publication can separate during failure; put-first artifact publication plus transactional references and outbox events provide recovery.

## Reversal path

Another ledger must pass the same port conformance, migration, concurrency, and append-only tests.

## Verification

Fresh-apply integration tests, extension checks, CAS tests, and append-only triggers verify the decision.
