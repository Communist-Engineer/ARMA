BEGIN;

CREATE TABLE idempotency_records (
    idempotency_key text PRIMARY KEY,
    operation_digest text NOT NULL CHECK (operation_digest ~ '^[a-f0-9]{64}$'),
    response jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE resource_measurements
    ADD COLUMN missing_reason_codes jsonb NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON TABLE idempotency_records IS
    'Stable mutation keys and semantic operation digests; response snapshots are immutable.';
COMMENT ON COLUMN resource_measurements.missing_reason_codes IS
    'Reason code for every null coordinate; zero remains reserved for a measured zero.';

CREATE TRIGGER idempotency_records_append_only
BEFORE UPDATE OR DELETE ON idempotency_records
FOR EACH ROW EXECUTE FUNCTION reject_event_mutation();

COMMIT;
