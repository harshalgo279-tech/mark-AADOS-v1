-- Migration: Email System Improvements
-- Date: 2026-01-14
-- Description: Adds new fields for email tracking, unsubscribe, and sequence scheduling
--
-- Run this migration against your MySQL database:
-- mysql -u root -p algonox_aados < 001_email_improvements.sql
--
-- Or connect to MySQL and run:
-- source /path/to/001_email_improvements.sql

-- =====================================================
-- LEADS TABLE: Add unsubscribe and email validation
-- =====================================================

-- Add unsubscribed_at for CAN-SPAM compliance
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS unsubscribed_at DATETIME(6) NULL;

-- Add email_valid for bounce tracking (defaults to true)
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS email_valid BOOLEAN DEFAULT TRUE NOT NULL;

-- =====================================================
-- EMAILS TABLE: Add tracking, scheduling, and error fields
-- =====================================================

-- Add preview_text for email clients
ALTER TABLE emails
ADD COLUMN IF NOT EXISTS preview_text VARCHAR(255) NULL;

-- Add scheduled_for for email sequence automation
ALTER TABLE emails
ADD COLUMN IF NOT EXISTS scheduled_for DATETIME(6) NULL;

-- Add tracking_id for open/click tracking
ALTER TABLE emails
ADD COLUMN IF NOT EXISTS tracking_id VARCHAR(64) NULL;

-- Add bounced_at for bounce tracking
ALTER TABLE emails
ADD COLUMN IF NOT EXISTS bounced_at DATETIME(6) NULL;

-- Add error_message for storing error details
ALTER TABLE emails
ADD COLUMN IF NOT EXISTS error_message TEXT NULL;

-- Add error_category for categorizing failures
ALTER TABLE emails
ADD COLUMN IF NOT EXISTS error_category VARCHAR(50) NULL;

-- Add retry_count for tracking retry attempts
ALTER TABLE emails
ADD COLUMN IF NOT EXISTS retry_count INT DEFAULT 0;

-- =====================================================
-- INDEXES: Add indexes for new fields
-- =====================================================

-- Index for tracking_id (unique lookups)
CREATE UNIQUE INDEX IF NOT EXISTS ix_emails_tracking_id ON emails(tracking_id);

-- Index for scheduled_for (scheduled email queries)
CREATE INDEX IF NOT EXISTS ix_emails_scheduled_for ON emails(scheduled_for);

-- Composite index for duplicate prevention
CREATE INDEX IF NOT EXISTS ix_emails_lead_type_date ON emails(lead_id, email_type, created_at);

-- =====================================================
-- Update existing datetime columns to timezone-aware
-- =====================================================

-- Note: If you have existing data, these ALTER TABLE statements
-- will convert existing DATETIME to DATETIME(6) for microsecond precision

ALTER TABLE emails
MODIFY COLUMN sent_at DATETIME(6) NULL,
MODIFY COLUMN delivered_at DATETIME(6) NULL,
MODIFY COLUMN opened_at DATETIME(6) NULL,
MODIFY COLUMN clicked_at DATETIME(6) NULL,
MODIFY COLUMN replied_at DATETIME(6) NULL,
MODIFY COLUMN created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6);

-- =====================================================
-- VERIFICATION QUERIES (run after migration)
-- =====================================================

-- Check leads table structure
-- DESCRIBE leads;

-- Check emails table structure
-- DESCRIBE emails;

-- Verify new columns exist
-- SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
-- WHERE TABLE_NAME = 'leads' AND COLUMN_NAME IN ('unsubscribed_at', 'email_valid');

-- SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
-- WHERE TABLE_NAME = 'emails' AND COLUMN_NAME IN ('preview_text', 'scheduled_for', 'tracking_id', 'bounced_at', 'error_message', 'error_category', 'retry_count');

SELECT 'Migration 001_email_improvements completed successfully' AS status;
