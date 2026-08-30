# Phase 1 dependency baseline

Resolved on **2026-08-12**. `uv.lock` is authoritative for Python transitive versions; `config/toolchain.lock.json` is authoritative for scientific executables.

| Component | Selected baseline | Upstream source | Rationale |
|---|---:|---|---|
| CPython | 3.14.7 | https://www.python.org/downloads/release/python-3147/ | Current stable 3.14 patch, released 2026-08-05 |
| uv | 0.11.33 | https://github.com/astral-sh/uv/releases/tag/0.11.33 | Current stable local resolver; bootstrap verifies the exact executable version |
| PostgreSQL | 18.4 | https://www.postgresql.org/docs/release/18.4/ | Current supported PostgreSQL 18 minor |
| pgvector | 0.8.6 | https://github.com/pgvector/pgvector/releases/tag/v0.8.6 | Reviewed vector-extension baseline; relational edges remain authoritative |
| Temporal Python SDK | 1.31.0 | https://github.com/temporalio/sdk-python/releases | Locked stable SDK resolved on Python 3.14 |
| CaDiCaL | 3.0.1 / `c607304…` | https://github.com/arminbiere/cadical | DRAT-generating solver process |
| DRAT-trim | `2e3b2dc…` | https://github.com/marijnheule/drat-trim | DRAT validation and LRAT conversion |
| cake_lpr | `a36874a…` | https://github.com/tanyongkiam/cake_lpr | independently built, formally verified final checker |

The execution host’s uv managed-runtime catalog supplied CPython 3.14.6 while upstream had published 3.14.7. Local verification therefore records 3.14.6 as the test interpreter; `.python-version` and CI retain the selected 3.14.7 baseline.

Direct Python packages and all transitives appear at exact versions in `uv.lock` and `sbom/amra-phase1.cdx.json`.

The local proof-tool build uses GCC/G++ 13.3.0, static linking, stripped binaries, a fixed CaDiCaL `SOURCE_DATE_EPOCH`, and a normalized build-system label. The executable SHA-256 values live in `config/toolchain.lock.json`. The GitHub proof-image job publishes the immutable image identities as a workflow artifact; their promotion into the lock remains a review gate before a binary/container release.
