-- Lead Ops Automation - Initial Schema
-- Run this if not using SQLAlchemy create_all (e.g. for production migrations)

-- leads: lead-centric view (one row per deterministic idempotency key)
CREATE TABLE IF NOT EXISTS leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key VARCHAR(64) UNIQUE NOT NULL,
    name VARCHAR(255),
    email VARCHAR(255),
    phone VARCHAR(50),
    status VARCHAR(32) NOT NULL DEFAULT 'new',
    owner VARCHAR(255),
    next_action_at TIMESTAMPTZ,
    next_action_note TEXT,
    latest_run_id UUID,
    latest_score INTEGER,
    latest_qualified BOOLEAN,
    latest_source VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_leads_idempotency_key ON leads(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_leads_email ON leads(email);
CREATE INDEX IF NOT EXISTS idx_leads_phone ON leads(phone);
CREATE INDEX IF NOT EXISTS idx_leads_status ON leads(status);

-- runs: full audit trail of every enrichment attempt
CREATE TABLE IF NOT EXISTS runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    idempotency_key VARCHAR(64),
    lead_id UUID REFERENCES leads(id),
    source VARCHAR(255) NOT NULL,
    workflow VARCHAR(64),
    payload_json JSONB NOT NULL,
    result_json JSONB,
    status VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'success', 'failed')),
    priority VARCHAR(20),
    scheduled_at VARCHAR(50),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_runs_idempotency_key ON runs(idempotency_key);
CREATE INDEX IF NOT EXISTS idx_runs_lead_id ON runs(lead_id);
CREATE INDEX IF NOT EXISTS idx_runs_created_at ON runs(created_at);
CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow);

-- idempotency_keys: deduplication - prevents duplicate processing
CREATE TABLE IF NOT EXISTS idempotency_keys (
    key VARCHAR(64) PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
