-- ICP (Ideal Customer Profile) and lead icp_score.
-- Safe to run multiple times.

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS icp_score INTEGER;

CREATE TABLE IF NOT EXISTS company_profile (
  id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  industry VARCHAR(255),
  company_size VARCHAR(64),
  budget_min NUMERIC,
  budget_max NUMERIC,
  intent_keywords JSONB DEFAULT '[]',
  location VARCHAR(255),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO company_profile (id, industry, company_size, budget_min, budget_max, intent_keywords, location, updated_at)
SELECT 1, NULL, NULL, NULL, NULL, '[]', NULL, now()
WHERE NOT EXISTS (SELECT 1 FROM company_profile WHERE id = 1);
