# Third-party notices

AMRA-authored source and documentation are licensed under DPL v1.0. The components below remain separately licensed works. Their inclusion in development or execution does not relicense them.

The exact Python inventory and package URLs appear in `sbom/amra-phase1.cdx.json`; `uv.lock` supplies exact versions and source hashes. Major separately executed components are:

| Component | Boundary | Source identity | License from upstream |
|---|---|---|---|
| CPython 3.14 | runtime | 3.14.7 | Python Software Foundation License |
| PostgreSQL | service | 18.4 | PostgreSQL License |
| pgvector | extension | 0.8.6 | PostgreSQL License |
| Temporal | service/SDK | SDK locked at 1.31.0 | MIT |
| MinIO-compatible object store | development service | image pin in Compose | AGPL-3.0 for MinIO server; confirm exact selected image notice |
| CaDiCaL | separate solver process | `c60730422e758ef1cebe7aeddf2dda31c996bf04` | MIT |
| DRAT-trim | separate converter/validator process | `2e3b2dc0ecf938addbd779d42877b6ed69d9a985` | MIT |
| cake_lpr | separate final-checker process | `a36874a8b750b43fe4b385b8ddbf5b033e46a3fa` | BSD-2-Clause |

Runtime libraries include FastAPI, Pydantic, SQLAlchemy, psycopg, Alembic, Temporal’s Python SDK, boto3, RFC 8785 canonicalization, OpenTelemetry API, PyYAML, Uvicorn, and their locked transitive dependencies. Development tools include pytest, Hypothesis, Ruff, Pyright, coverage, pip-audit, CycloneDX tooling, JSON Schema validators, and their transitives. Each package’s upstream metadata and license files govern that package.

OCI base-image copyrights and license files must be copied into release artifacts. Datasets, papers, DIMACS inputs, DRAT/LRAT proofs, and generated evidence retain their own provenance and terms; content addressing supplies identity rather than a license change.

The DPL compatibility question for combined binary/container distribution remains a release gate documented in `docs/legal/DPL_DEPENDENCY_INTERPRETATION_REQUIRED.md`.
