-- Lead Ops Automation - Initial Schema
-- Run this if not using SQLAlchemy create_all (e.g. for production migrations)

-- runs: full audit trail of every enrichment attempt
CREATE TABLE IF NOT EXISTS runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key VARCHAR(64),
    source VARCHAR(255) NOT NULL,
    payload_json JSONB NOT NULL,
    result_json JSONB,
    status VARCHAR(20) NOT NULL CHECK (status IN ('success', 'failed')),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_runs_idempotency_key ON runs(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);

-- idempotency_keys: deduplication - prevents duplicate processing
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key VARCHAR(64) PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
