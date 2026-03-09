-- Introduce lead-centric storage.
-- Safe to run multiple times.

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

ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS lead_id UUID REFERENCES leads(id);

CREATE INDEX IF NOT EXISTS idx_runs_lead_id ON runs(lead_id);
