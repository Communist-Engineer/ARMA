# License Steward Council interpretation required

The DPL v1.0 ethical-copyleft clause calls ordinary MIT, Apache-2.0, BSD, ISC, MPL, LGPL, and GPL licenses incompatible. Phase 1 uses separately licensed components to build and test the development system. Governance interpretation remains necessary for these concrete combinations:

1. Importing permissively licensed Python libraries into a DPL-authored Python process and distributing the combined environment or wheel.
2. Linking `psycopg-binary`, `pydantic-core`, `greenlet`, and Temporal’s native runtime into a distributed application image.
3. Aggregating AMRA code with PostgreSQL, pgvector, Temporal, and an S3-compatible server in one Compose distribution.
4. Distributing solver, converter, and checker images that contain CaDiCaL, DRAT-trim, cake_lpr, a C/C++ runtime, and OCI base layers.
5. Reproducing third-party license text or generated SBOM metadata inside the DPL repository.
6. Treating generated DRAT/LRAT proofs, benchmark instances, papers, or datasets as repository artifacts when their copyright status differs from AMRA source.

The requested interpretation should distinguish mere aggregation, dynamic import, native linking, container layering, build-time use, and independently invoked executables. It should also specify notice placement, source-offer duties, and whether a DPL declaration can cover only AMRA-authored layers.

**Release gate:** maintainers may develop and test the Phase 1 system and publish DPL-authored source with preserved third-party notices. A public binary/container distribution may be described as fully DPL-compliant only after an authoritative interpretation or compatible-license decision covers the exact composition.

Owner: License Steward Council and AMRA maintainer. Proposed resolution: file a governance request containing the SBOM, image layer inventory, and this concrete combination list.
