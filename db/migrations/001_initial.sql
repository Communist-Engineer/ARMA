BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TYPE obligation_state AS ENUM (
    'DRAFT',
    'READY',
    'RESERVED',
    'RUNNING',
    'AWAITING_EVIDENCE',
    'AWAITING_REVIEW',
    'AWAITING_HUMAN',
    'SUCCEEDED',
    'FAILED',
    'CANCELLED',
    'HELD'
);

CREATE TYPE claim_status AS ENUM (
    'PROPOSED',
    'EMPIRICALLY_SUPPORTED',
    'ADVERSARIALLY_TESTED',
    'MACHINE_CERTIFIED',
    'INDEPENDENTLY_RECONSTRUCTED',
    'FORMALLY_PROVED',
    'REFUTED',
    'PROCEDURALLY_HELD'
);

CREATE TYPE evidence_kind AS ENUM (
    'MODEL_PROPOSAL',
    'TEST_REPORT',
    'EXPERIMENT',
    'COUNTEREXAMPLE',
    'CERTIFICATE',
    'CHECKER_REPORT',
    'INDEPENDENT_REVIEW',
    'BLIND_RECONSTRUCTION',
    'LEAN_PROOF',
    'HUMAN_REVIEW'
);

CREATE TYPE evidence_disposition AS ENUM (
    'PENDING',
    'ACCEPTED',
    'REJECTED',
    'SUPERSEDED',
    'HELD'
);

CREATE TYPE semantic_relation AS ENUM (
    'EQUIVALENCE',
    'EQUISATISFIABILITY',
    'PROJECTION',
    'REDUCTION',
    'APPROXIMATION'
);

CREATE TYPE cost_state AS ENUM (
    'RESERVED',
    'DEBITED',
    'RELEASED',
    'RECONCILED',
    'QUARANTINED'
);

CREATE TABLE programs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL UNIQUE,
    charter_version text NOT NULL,
    state text NOT NULL DEFAULT 'ACTIVE',
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE artifacts (
    digest text PRIMARY KEY CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
    size_bytes bigint NOT NULL CHECK (size_bytes >= 0),
    media_type text NOT NULL,
    storage_uri text NOT NULL,
    canonicalization text,
    retention_class text NOT NULL DEFAULT 'STANDARD',
    retention_until timestamptz,
    legal_hold boolean NOT NULL DEFAULT false,
    signature_digest text REFERENCES artifacts(digest),
    created_at timestamptz NOT NULL DEFAULT now(),
    created_by text NOT NULL
);

CREATE TABLE representation_types (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL,
    version text NOT NULL,
    schema_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    semantics_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, version),
    UNIQUE (name, version)
);

CREATE TABLE transforms (
    id uuid NOT NULL DEFAULT gen_random_uuid(),
    name text NOT NULL,
    version text NOT NULL,
    source_representation_id uuid NOT NULL,
    source_representation_version text NOT NULL,
    target_representation_id uuid NOT NULL,
    target_representation_version text NOT NULL,
    relation semantic_relation NOT NULL,
    specification_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    implementation_artifact_digest text REFERENCES artifacts(digest),
    checker_artifact_digest text REFERENCES artifacts(digest),
    resource_bound_artifact_digest text REFERENCES artifacts(digest),
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (id, version),
    UNIQUE (name, version),
    FOREIGN KEY (source_representation_id, source_representation_version)
        REFERENCES representation_types(id, version),
    FOREIGN KEY (target_representation_id, target_representation_version)
        REFERENCES representation_types(id, version)
);

CREATE TABLE claims (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id uuid NOT NULL REFERENCES programs(id),
    title text NOT NULL,
    informal_statement text NOT NULL,
    informal_statement_digest text NOT NULL CHECK (
        informal_statement_digest ~ '^sha256:[a-f0-9]{64}$'
    ),
    status claim_status NOT NULL DEFAULT 'PROPOSED',
    priority integer NOT NULL DEFAULT 0,
    owner text,
    supersedes_claim_id uuid REFERENCES claims(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE formal_statements (
    digest text PRIMARY KEY CHECK (digest ~ '^sha256:[a-f0-9]{64}$'),
    language text NOT NULL,
    statement_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    toolchain_artifact_digest text REFERENCES artifacts(digest),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE claim_formal_statements (
    claim_id uuid NOT NULL REFERENCES claims(id),
    formal_statement_digest text NOT NULL REFERENCES formal_statements(digest),
    semantic_delta text NOT NULL,
    semantic_delta_artifact_digest text REFERENCES artifacts(digest),
    reviewed_by text,
    reviewed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (claim_id, formal_statement_digest)
);

CREATE TABLE claim_dependencies (
    claim_id uuid NOT NULL REFERENCES claims(id),
    depends_on_claim_id uuid NOT NULL REFERENCES claims(id),
    relation text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (claim_id, depends_on_claim_id, relation),
    CHECK (claim_id <> depends_on_claim_id)
);

CREATE TABLE obligations (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id uuid NOT NULL REFERENCES programs(id),
    claim_id uuid REFERENCES claims(id),
    parent_obligation_id uuid REFERENCES obligations(id),
    objective text NOT NULL,
    packet_artifact_digest text REFERENCES artifacts(digest),
    state obligation_state NOT NULL DEFAULT 'DRAFT',
    state_version bigint NOT NULL DEFAULT 0 CHECK (state_version >= 0),
    policy_versions jsonb NOT NULL DEFAULT '{}'::jsonb,
    budget_currency char(3) NOT NULL DEFAULT 'USD',
    model_budget numeric(18,6) NOT NULL DEFAULT 0 CHECK (model_budget >= 0),
    sandbox_budget numeric(18,6) NOT NULL DEFAULT 0 CHECK (sandbox_budget >= 0),
    solver_budget numeric(18,6) NOT NULL DEFAULT 0 CHECK (solver_budget >= 0),
    search_budget numeric(18,6) NOT NULL DEFAULT 0 CHECK (search_budget >= 0),
    verification_reserve numeric(18,6) NOT NULL DEFAULT 0 CHECK (verification_reserve >= 0),
    maximum_frontier_calls integer NOT NULL DEFAULT 0 CHECK (maximum_frontier_calls >= 0),
    deadline timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (parent_obligation_id IS NULL OR parent_obligation_id <> id)
);

CREATE TABLE attempts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    obligation_id uuid NOT NULL REFERENCES obligations(id),
    attempt_number integer NOT NULL CHECK (attempt_number > 0),
    actor_kind text NOT NULL,
    actor_ref text NOT NULL,
    provider_family text,
    model_alias text,
    independence_role text NOT NULL,
    scratch_namespace text NOT NULL UNIQUE,
    state text NOT NULL,
    provider_request_id text,
    execution_backend_id text,
    lease_owner text,
    lease_expires_at timestamptz,
    started_at timestamptz,
    ended_at timestamptz,
    raw_receipt_artifact_digest text REFERENCES artifacts(digest),
    execution_manifest_digest text REFERENCES artifacts(digest),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (obligation_id, attempt_number)
);

CREATE TABLE experiments (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    obligation_id uuid NOT NULL REFERENCES obligations(id),
    claim_id uuid REFERENCES claims(id),
    manifest_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    manifest_frozen_at timestamptz NOT NULL,
    state text NOT NULL,
    reproducibility_level text NOT NULL CHECK (
        reproducibility_level IN ('R0', 'R1', 'R2', 'R3', 'R4')
    ),
    parent_experiment_id uuid REFERENCES experiments(id),
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evidence (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id uuid NOT NULL REFERENCES claims(id),
    obligation_id uuid REFERENCES obligations(id),
    attempt_id uuid REFERENCES attempts(id),
    experiment_id uuid REFERENCES experiments(id),
    kind evidence_kind NOT NULL,
    disposition evidence_disposition NOT NULL DEFAULT 'PENDING',
    content_digest text CHECK (
        content_digest IS NULL OR content_digest ~ '^sha256:[a-f0-9]{64}$'
    ),
    artifact_digest text REFERENCES artifacts(digest),
    summary text NOT NULL,
    supersedes_evidence_id uuid REFERENCES evidence(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz,
    decided_by text,
    CHECK (content_digest IS NOT NULL OR artifact_digest IS NOT NULL),
    CHECK (supersedes_evidence_id IS NULL OR supersedes_evidence_id <> id)
);

CREATE TABLE reviews (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id uuid NOT NULL REFERENCES claims(id),
    evidence_id uuid REFERENCES evidence(id),
    attempt_id uuid NOT NULL REFERENCES attempts(id),
    reviewer_family text,
    blind boolean NOT NULL DEFAULT false,
    disposition evidence_disposition NOT NULL DEFAULT 'PENDING',
    review_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    shared_artifacts jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz
);

CREATE TABLE certificate_registry (
    certificate_type text NOT NULL,
    version text NOT NULL,
    media_type text NOT NULL,
    checker_image_digest text NOT NULL,
    checker_command text NOT NULL,
    soundness_scope_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    test_corpus_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    trust_tier text NOT NULL,
    owner text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (certificate_type, version)
);

CREATE TABLE certificates (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    evidence_id uuid NOT NULL REFERENCES evidence(id),
    certificate_type text NOT NULL,
    certificate_version text NOT NULL,
    certificate_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    checker_report_artifact_digest text REFERENCES artifacts(digest),
    checker_outcome text NOT NULL CHECK (
        checker_outcome IN ('PENDING', 'ACCEPTED', 'REJECTED', 'ERROR')
    ),
    checked_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (certificate_type, certificate_version)
        REFERENCES certificate_registry(certificate_type, version)
);

CREATE TABLE resource_measurements (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    experiment_id uuid REFERENCES experiments(id),
    attempt_id uuid REFERENCES attempts(id),
    transform_id uuid,
    transform_version text,
    path_position integer CHECK (path_position IS NULL OR path_position >= 0),
    discovery_time_ms numeric CHECK (discovery_time_ms IS NULL OR discovery_time_ms >= 0),
    execution_time_ms numeric CHECK (execution_time_ms IS NULL OR execution_time_ms >= 0),
    verification_time_ms numeric CHECK (verification_time_ms IS NULL OR verification_time_ms >= 0),
    peak_memory_bytes bigint CHECK (peak_memory_bytes IS NULL OR peak_memory_bytes >= 0),
    width numeric CHECK (width IS NULL OR width >= 0),
    algebraic_degree numeric CHECK (algebraic_degree IS NULL OR algebraic_degree >= 0),
    rank numeric CHECK (rank IS NULL OR rank >= 0),
    precision_bits numeric CHECK (precision_bits IS NULL OR precision_bits >= 0),
    advice_bits numeric CHECK (advice_bits IS NULL OR advice_bits >= 0),
    aggregate_parallel_work numeric CHECK (
        aggregate_parallel_work IS NULL OR aggregate_parallel_work >= 0
    ),
    communication_bytes bigint CHECK (communication_bytes IS NULL OR communication_bytes >= 0),
    random_bits numeric CHECK (random_bits IS NULL OR random_bits >= 0),
    monetary_cost numeric(18,6) CHECK (monetary_cost IS NULL OR monetary_cost >= 0),
    extra_resources jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (experiment_id IS NOT NULL OR attempt_id IS NOT NULL),
    FOREIGN KEY (transform_id, transform_version) REFERENCES transforms(id, version)
);

CREATE TABLE promotion_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id uuid NOT NULL REFERENCES claims(id),
    from_status claim_status NOT NULL,
    to_status claim_status NOT NULL,
    policy_version text NOT NULL,
    evidence_ids uuid[] NOT NULL,
    decision_artifact_digest text NOT NULL REFERENCES artifacts(digest),
    actor text NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_status <> to_status)
);

CREATE TABLE cost_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    program_id uuid NOT NULL REFERENCES programs(id),
    obligation_id uuid REFERENCES obligations(id),
    attempt_id uuid REFERENCES attempts(id),
    provider text NOT NULL,
    category text NOT NULL,
    state cost_state NOT NULL,
    currency char(3) NOT NULL DEFAULT 'USD',
    amount numeric(18,6) NOT NULL CHECK (amount >= 0),
    price_book_version text,
    provider_receipt_artifact_digest text REFERENCES artifacts(digest),
    provider_event_id text,
    idempotency_key text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    reconciled_at timestamptz
);

CREATE TABLE outbox_events (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    aggregate_type text NOT NULL,
    aggregate_id uuid NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL,
    idempotency_key text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz,
    publish_attempts integer NOT NULL DEFAULT 0 CHECK (publish_attempts >= 0)
);

CREATE INDEX claims_program_status_idx ON claims(program_id, status);
CREATE INDEX obligations_program_state_idx ON obligations(program_id, state);
CREATE INDEX obligations_claim_idx ON obligations(claim_id);
CREATE INDEX attempts_obligation_state_idx ON attempts(obligation_id, state);
CREATE INDEX experiments_claim_idx ON experiments(claim_id);
CREATE INDEX evidence_claim_kind_idx ON evidence(claim_id, kind, disposition);
CREATE INDEX cost_events_obligation_idx ON cost_events(obligation_id, created_at);
CREATE INDEX outbox_unpublished_idx ON outbox_events(created_at) WHERE published_at IS NULL;

CREATE FUNCTION set_updated_at() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

CREATE TRIGGER programs_set_updated_at
BEFORE UPDATE ON programs
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER claims_set_updated_at
BEFORE UPDATE ON claims
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE TRIGGER obligations_set_updated_at
BEFORE UPDATE ON obligations
FOR EACH ROW EXECUTE FUNCTION set_updated_at();

CREATE FUNCTION protect_artifact_identity() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.digest <> OLD.digest
       OR NEW.size_bytes <> OLD.size_bytes
       OR NEW.media_type <> OLD.media_type
       OR NEW.storage_uri <> OLD.storage_uri
       OR NEW.created_at <> OLD.created_at
       OR NEW.created_by <> OLD.created_by THEN
        RAISE EXCEPTION 'artifact identity and content metadata are immutable';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER artifacts_protect_identity
BEFORE UPDATE ON artifacts
FOR EACH ROW EXECUTE FUNCTION protect_artifact_identity();

CREATE FUNCTION enforce_formal_promotion() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    has_reviewed_statement boolean;
    has_accepted_lean_evidence boolean;
BEGIN
    IF NEW.to_status <> 'FORMALLY_PROVED' THEN
        RETURN NEW;
    END IF;

    SELECT EXISTS (
        SELECT 1
        FROM claim_formal_statements cfs
        WHERE cfs.claim_id = NEW.claim_id
          AND cfs.reviewed_at IS NOT NULL
          AND cfs.reviewed_by IS NOT NULL
    ) INTO has_reviewed_statement;

    SELECT EXISTS (
        SELECT 1
        FROM evidence e
        WHERE e.claim_id = NEW.claim_id
          AND e.kind = 'LEAN_PROOF'
          AND e.disposition = 'ACCEPTED'
          AND e.id = ANY (NEW.evidence_ids)
    ) INTO has_accepted_lean_evidence;

    IF NOT has_reviewed_statement OR NOT has_accepted_lean_evidence THEN
        RAISE EXCEPTION 'formal promotion requires a reviewed formal statement and accepted Lean evidence';
    END IF;

    RETURN NEW;
END;
$$;

CREATE TRIGGER promotion_requires_formal_evidence
BEFORE INSERT ON promotion_events
FOR EACH ROW EXECUTE FUNCTION enforce_formal_promotion();

CREATE FUNCTION reject_event_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
END;
$$;

CREATE TRIGGER promotion_events_append_only
BEFORE UPDATE OR DELETE ON promotion_events
FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();

CREATE TRIGGER cost_events_append_only
BEFORE UPDATE OR DELETE ON cost_events
FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();

COMMENT ON TABLE promotion_events IS
    'Append-only promotion decisions. Claim status projection is updated transactionally by the application.';
COMMENT ON TABLE cost_events IS
    'Append-only economic ledger. Corrections are compensating events, never mutations.';
COMMENT ON COLUMN resource_measurements.aggregate_parallel_work IS
    'Aggregate work across parallel workers; wall-clock speedup cannot conceal this resource.';

COMMIT;
