-- Add follow-up scheduling fields to leads.
-- Safe to run multiple times.

ALTER TABLE leads
  ADD COLUMN IF NOT EXISTS next_action_at TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS next_action_note TEXT;

