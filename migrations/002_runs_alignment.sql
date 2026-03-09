-- Align existing runs table with current application model.
-- Safe to run multiple times.

-- 1) Ensure columns exist
ALTER TABLE runs
  ADD COLUMN IF NOT EXISTS workflow VARCHAR(64),
  ADD COLUMN IF NOT EXISTS priority VARCHAR(20),
  ADD COLUMN IF NOT EXISTS scheduled_at VARCHAR(50),
  ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ;

-- 2) Ensure status check allows pending/success/failed
DO $$
DECLARE
  c RECORD;
BEGIN
  -- Drop any CHECK constraints on runs that reference the "status" column
  FOR c IN
    SELECT conname
    FROM pg_constraint
    WHERE conrelid = 'runs'::regclass
      AND contype = 'c'
      AND pg_get_constraintdef(oid) ILIKE '%status%'
  LOOP
    EXECUTE format('ALTER TABLE runs DROP CONSTRAINT IF EXISTS %I', c.conname);
  END LOOP;

  -- Re-add canonical status constraint
  EXECUTE $q$
    ALTER TABLE runs
    ADD CONSTRAINT runs_status_check CHECK (status IN ('pending', 'success', 'failed'))
  $q$;
END $$;

-- 3) Helpful indexes
CREATE INDEX IF NOT EXISTS idx_runs_workflow ON runs(workflow);
