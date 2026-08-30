# ADR-001: Python 3.14 and uv

## Context

Phase 1 needs one reproducible Python line across development, CI, API, and Temporal workers.

## Decision

Use CPython 3.14.7 with `requires-python = ">=3.14,<3.15"`, `.python-version`, uv 0.11.33, and committed `uv.lock`. CI uses locked resolution. Stable public APIs receive preference.

## Alternatives considered

Python 3.13 offered broader historical wheel coverage. Loose pip requirements offered faster scaffolding. Both weakened the fixed Phase 1 baseline.

## Material consequences

Every supported environment needs a 3.14 runtime and uv. Native-wheel availability becomes an explicit gate. The local host tested 3.14.6 because uv’s managed catalog lagged upstream 3.14.7.

## Failure modes

Runtime catalog lag, absent wheels, resolver drift, or a mutable uv installer can break bootstrap.

## Reversal path

Adopt another patch within 3.14 through a reviewed lock update. A minor-line change requires a successor ADR and replay/migration verification.

## Verification

CI checks Python, uv, `uv sync --locked`, lock cleanliness, tests, typing, and SBOM agreement.
