# ADR-006: Temporal determinism, idempotency, and versioning

## Context

Worker loss may occur after an expensive solver side effect and before activity acknowledgment.

## Decision

`SatVerificationWorkflow` orchestrates only. Activities own filesystem, hashing, database, subprocess, object storage, clock, and cost work. Every activity receives an explicit key, heartbeats a checkpoint, and returns a content digest. The workflow uses patch marker `amra-phase1-sat-workflow-v1`; manifests record build ID `amra-phase1-v1`.

## Alternatives considered

An in-process task queue lacked history replay. Performing I/O in workflow code violated Temporal replay semantics.

## Material consequences

Activity handlers need durable deduplication. Invalid scientific evidence and budget exhaustion are non-retryable; infrastructure and interruption failures use bounded retry.

## Failure modes

Nondeterministic imports, changed workflow code without versioning, missing heartbeats, or conflicting keys can corrupt recovery semantics.

## Reversal path

Deploy a new workflow type/build ID, replay recorded histories, then drain the earlier build.

## Verification

Time-skipping tests, typed signal tests, history replay fixtures, and a post-solver durable-side-effect recovery test exercise the boundary.
