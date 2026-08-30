# Dependency license policy

AMRA Cloud is DPL-licensed commons software. Dependencies remain separate works under their own licenses and retain their notices, copyright, source provenance, and distribution conditions.

## Admission rules

Every dependency change requires a locked version, source identity, license identification, vulnerability review, and placement in one category: runtime library, development tool, separately executed proof tool, OCI base image, dataset, paper, or generated proof artifact. Provider imports remain inside adapters. Scientific generators and final checkers remain separate processes.

Dependencies with missing, ambiguous, source-inconsistent, or nonredistributable terms block release packaging. Permissive and copyleft labels alone never establish DPL compatibility. `THIRD_PARTY_NOTICES.md` and the CycloneDX SBOM are generated from the lock and pinned tool registry, then reviewed as release artifacts.

## Distribution boundary

Source development may use separately licensed dependencies while preserving their boundaries. A public binary or container combining AMRA-authored code with dependencies requires the License Steward Council interpretation described in `DPL_DEPENDENCY_INTERPRETATION_REQUIRED.md`. Until that interpretation exists, release metadata describes AMRA as ethical source-available software or DPL-licensed commons software and makes no compatibility claim.

Proof artifacts and research inputs preserve source-specific terms and provenance. Their presence in content-addressed storage never changes their license.
