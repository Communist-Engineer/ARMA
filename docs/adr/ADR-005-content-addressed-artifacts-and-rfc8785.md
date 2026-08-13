# ADR-005: Content-addressed artifacts and RFC 8785

## Context

Scientific inputs require exact-byte identity while manifests require cross-runtime canonical JSON.

## Decision

Raw inputs retain exact bytes. Identity is `sha256:<lowercase hex>`. JSON uses RFC 8785. Local publication uses a temporary file, flush, fsync, atomic rename, directory fsync, and verified read. S3 uses conditional creation and verified reads.

## Alternatives considered

Filename identity and ordinary JSON encoding admitted substitution or serializer drift. Database byte storage mixed large immutable content with relational authority.

## Material consequences

Metadata lives alongside local objects for reconstruction and in PostgreSQL for authority. Every scientific read pays a hash-verification cost.

## Failure modes

Corrupt bytes, missing metadata, interrupted temporary files, and concurrent writes produce typed failures or idempotent equality.

## Reversal path

Add a new digest/canonicalization version while retaining existing identities and explicit derivation edges.

## Verification

Unit tests cover corruption, missing objects, interrupted writes, concurrency, equal writes, and conflicts.
