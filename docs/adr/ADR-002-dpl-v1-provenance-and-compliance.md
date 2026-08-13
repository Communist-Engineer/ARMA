# ADR-002: DPL v1.0 provenance and compliance

## Context

The DPL governance repository’s pinned `LICENSE.md` identifies v1.0 while its README and compliance template contain v1.2 references.

## Decision

Use the exact v1.0 bytes at commit `13abdac…`, SHA-256 `ed7031dd…`. Correct the project declaration label, preserve the discrepancy in provenance, and leave personal attestations for human ratification.

## Alternatives considered

Following the README’s v1.2 label lacked a matching legal text. Editing the license would destroy canonical provenance.

## Material consequences

AMRA is DPL-licensed commons software and ethical source-available software; project metadata avoids an unqualified OSI “open source” claim.

## Failure modes

Byte drift, premature personal attestation, or an unsupported dependency-compatibility claim could invalidate the declaration.

## Reversal path

A reviewed maintainer decision may adopt a later canonical DPL artifact through a new commit, provenance record, and declaration amendment.

## Verification

CI hashes `LICENSE.md` and checks the compliance, provenance, registry, policy, notices, and SBOM artifacts.
