# ADR-010: Third-party license boundaries and SBOM

## Context

AMRA’s DPL authorship coexists with permissive, copyleft, service, compiler-runtime, dataset, paper, and proof-artifact licenses.

## Decision

Preserve each component’s original terms and classify its boundary. Generate a reproducible CycloneDX SBOM from `uv.lock` plus the pinned proof-tool registry. Maintain notices and a concrete DPL interpretation request. Treat fully DPL-compliant public binary/container distribution as a governance gate.

## Alternatives considered

Calling all dependencies “compatible” lacked governance authority. Excluding build and scientific tools left the execution trust chain incomplete.

## Material consequences

Source development proceeds with separated dependencies. Release review includes Python libraries, native wheels, services, OCI bases, solver tools, datasets, papers, and generated artifacts.

## Failure modes

Missing license metadata, unpinned tools, omitted OCI layers, or a compatibility assertion can block release.

## Reversal path

Replace a dependency, isolate it further, or apply a future License Steward Council interpretation through an amendment commit.

## Verification

CI compares lock and SBOM component sets, checks tool commits, verifies notices, and runs vulnerability/license policy gates.
