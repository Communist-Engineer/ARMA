# AMRA Cloud

AMRA Cloud is the engineering substrate for the **Exact Adaptive Multiscale Representation Atlas** research program. It coordinates model-assisted mathematical work while keeping mathematical authority in deterministic programs, explicit certificates, reproducible experiments, and formal proof systems.

> Models propose; programs test; certificates verify; formal systems promote.

## Current status

The Phase 1 vertical slice ingests exact DIMACS bytes, content-addresses them, reserves a synthetic budget, executes CaDiCaL, independently checks SAT assignments or converts DRAT to LRAT and checks it with cake_lpr, records a complete resource vector, finalizes a canonical manifest, and reproduces the result from referenced artifacts. It defines research infrastructure and makes no P-versus-NP claim.

## Specification set

- [`docs/system-specification.md`](docs/system-specification.md) — normative architecture, workflows, trust model, infrastructure modules, controls, and acceptance gates
- [`config/model-routing.yaml`](config/model-routing.yaml) — provider-neutral routing policy and escalation controls
- [`config/budgets.yaml`](config/budgets.yaml) — pilot envelopes and enforcement thresholds
- [`schemas/obligation-packet.schema.json`](schemas/obligation-packet.schema.json) — task handoff contract
- [`db/migrations/001_initial.sql`](db/migrations/001_initial.sql) — initial theorem and experiment ledger

## Design invariants

1. A model response is never workflow state or mathematical authority.
2. Every promoted claim is linked to immutable inputs, code, environment, outputs, and a checker.
3. Discovery cost and every hidden computational resource are charged to the representation path.
4. Construction and adversarial review use independent execution contexts and, at promotion-sensitive stages, different model families.
5. The portable domain core depends on provider-neutral ports; AWS, Modal, Temporal, and model vendors enter through adapters.
6. Formal statements, informal claims, and the delta between them remain separate ledger objects.

## Initial implementation sequence

1. Implement the ledger and content-addressed artifact contracts.
2. Implement the deterministic Temporal-compatible obligation state machine in a local development profile.
3. Add one model adapter, one sandbox adapter, and one solver adapter.
4. Close one end-to-end SAT certificate path before adding providers or concurrency.
5. Add adversarial review, blind reconstruction, and Lean promotion gates.
6. Deploy the three-month cloud pilot only after the specification's readiness gates pass.

## Phase 1 quick start

Prerequisites are uv 0.11.33, Git, Make, a C/C++ compiler, and optionally Docker Compose for PostgreSQL, Temporal, and MinIO-compatible integration services.

```bash
make bootstrap
make verify
make demo
```

`make bootstrap` selects CPython 3.14.7, performs `uv sync --locked`, builds the three source-pinned proof executables, and regenerates the CycloneDX SBOM. A development host whose uv runtime catalog still supplies 3.14.6 can run `make bootstrap PYTHON_VERSION=3.14.6`; the selected project baseline remains 3.14.7.

The demonstration prints the obligation and artifact identities, solver outcome, independent checker report, resource/cost disposition, manifest digest, and exact reproduction command.

Operator commands include:

```text
amra db migrate
amra artifact put FILE
amra obligation create PACKET
amra obligation run ID
amra obligation show ID
amra demo trust-loop [CNF]
amra reproduce MANIFEST_DIGEST
amra verify MANIFEST_DIGEST
```

`make services` starts digest-pinned PostgreSQL 18 plus pgvector, Temporal, and MinIO-compatible services. `make clean` removes only the `amra-phase1` Compose project, its named local volumes, and AMRA-generated artifact/work directories.

## Scientific trust boundary

The UNSAT path uses three separately built executables:

```text
CaDiCaL → DRAT proof → DRAT-trim → LRAT certificate → cake_lpr
```

Commands use explicit argument arrays. Scientific container jobs use read-only roots, resource ceilings, and `--network=none`. The final checker image contains cake_lpr and its runtime while excluding solver code. SAT models enter a separate strict Python process that rejects partial, duplicated, contradictory, out-of-range, or clause-failing assignments.

Temporal owns orchestration, retry, signals, and recovery. Filesystem, hashing, subprocess, clock, database, object storage, and cost work stay in activities. Activity results are durably journaled before acknowledgment, so replacement workers reuse solver output and preserve one logical cost reconciliation.

## Reproducibility and supply chain

- `.python-version`, `uv.lock`, and `docs/dependency-baseline.md` freeze the Python baseline.
- `config/toolchain.lock.json` freezes proof-tool source commits; CI records each built image identity as an artifact.
- External Compose and CI services use version-plus-digest references.
- `sbom/amra-phase1.cdx.json` inventories the locked Python environment and proof tools.
- Alembic verifies the exact historical migration checksum and takes a PostgreSQL advisory lock.
- RFC 8785 canonical JSON and read-time SHA-256 verification govern manifests and scientific artifacts.

## Naming

The scientific program is **AMRA**. The repository currently retains its original GitHub name, `ARMA`.

## License

AMRA-authored source and documentation are DPL-licensed commons software under the exact Dialectical Public License v1.0 bytes in [`LICENSE.md`](LICENSE.md). Third-party components retain their original licenses. Public binary/container distribution carries the governance gate documented in [`docs/legal/DPL_DEPENDENCY_INTERPRETATION_REQUIRED.md`](docs/legal/DPL_DEPENDENCY_INTERPRETATION_REQUIRED.md).
