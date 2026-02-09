-- Migration: Add CBR risk fields to companies table
-- Date: 2026-02-09
-- Description: Add fields for storing CBR (Central Bank of Russia) risk assessment data

-- Add CBR risk fields to companies table
ALTER TABLE companies
ADD COLUMN IF NOT EXISTS cbr_risk_level VARCHAR(50),
ADD COLUMN IF NOT EXISTS cbr_risk_facts JSONB,
ADD COLUMN IF NOT EXISTS cbr_checked_at TIMESTAMP;

-- Add comment to explain the fields
COMMENT ON COLUMN companies.cbr_risk_level IS 'CBR risk level: success, warning, danger';
COMMENT ON COLUMN companies.cbr_risk_facts IS 'CBR risk factors (JSON with danger and warning arrays)';
COMMENT ON COLUMN companies.cbr_checked_at IS 'Timestamp when CBR risk was last checked';
