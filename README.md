# AMRA Cloud

AMRA Cloud is the engineering substrate for the **Exact Adaptive Multiscale Representation Atlas** research program. It coordinates model-assisted mathematical work while keeping mathematical authority in deterministic programs, explicit certificates, reproducible experiments, and formal proof systems.

> Models propose; programs test; certificates verify; formal systems promote.

## Current status

This repository currently contains the v0.1 system specification and its first machine-readable contracts. It defines the pilot architecture; it does not claim a result about P versus NP.

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

## Naming

The scientific program is **AMRA**. The repository currently retains its original GitHub name, `ARMA`.

## License

No license has been selected yet. Until a license is added, ordinary copyright rules apply.
