-- Migration: Email Intelligence System
-- Date: 2026-01-14
-- Description: Adds AI-powered email intelligence features including
--              engagement scoring, A/B testing, reply analysis, and warmup tracking
--
-- Run this migration after 001_email_improvements.sql:
-- mysql -u root -p algonox_aados < 002_email_intelligence.sql

-- =====================================================
-- LEADS TABLE: Add email intelligence fields
-- =====================================================

-- Engagement score (calculated from email interactions)
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS email_engagement_score INT DEFAULT 0;

-- Engagement level: hot, warm, lukewarm, cold, dead
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS email_engagement_level VARCHAR(20) DEFAULT 'cold';

-- Optimal send time (hour of day in UTC, 0-23)
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS email_optimal_hour INT NULL;

-- Optimal send day (0=Monday, 6=Sunday)
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS email_optimal_day INT NULL;

-- Timezone (inferred from company location)
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS timezone VARCHAR(50) NULL;

-- Last engagement score calculation timestamp
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS engagement_calculated_at DATETIME(6) NULL;

-- Reply sentiment from last email reply (-1 to 1)
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS last_reply_sentiment FLOAT NULL;

-- Reply intent classification
ALTER TABLE leads
ADD COLUMN IF NOT EXISTS last_reply_intent VARCHAR(50) NULL;

-- Index for engagement-based queries
CREATE INDEX IF NOT EXISTS ix_leads_engagement ON leads(email_engagement_level, email_engagement_score DESC);

-- =====================================================
-- EMAIL A/B TESTS TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS email_ab_tests (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email_type VARCHAR(100) NOT NULL,
    test_type VARCHAR(50) NOT NULL DEFAULT 'subject',
    status VARCHAR(20) DEFAULT 'active',
    winner_variant_id INT NULL,
    min_sample_size INT DEFAULT 50,
    confidence_threshold FLOAT DEFAULT 0.95,
    results_summary JSON NULL,
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    started_at DATETIME(6) NULL,
    completed_at DATETIME(6) NULL,
    INDEX ix_ab_tests_status (status),
    INDEX ix_ab_tests_email_type (email_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- EMAIL A/B TEST VARIANTS TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS email_ab_test_variants (
    id INT AUTO_INCREMENT PRIMARY KEY,
    test_id INT NOT NULL,
    variant_name VARCHAR(100) NOT NULL,
    variant_content TEXT NOT NULL,
    variant_approach VARCHAR(100) NULL,
    is_control BOOLEAN DEFAULT FALSE,
    emails_sent INT DEFAULT 0,
    emails_opened INT DEFAULT 0,
    emails_clicked INT DEFAULT 0,
    emails_replied INT DEFAULT 0,
    emails_converted INT DEFAULT 0,
    open_rate FLOAT DEFAULT 0.0,
    click_rate FLOAT DEFAULT 0.0,
    reply_rate FLOAT DEFAULT 0.0,
    conversion_rate FLOAT DEFAULT 0.0,
    is_winner BOOLEAN DEFAULT FALSE,
    lift_vs_control FLOAT NULL,
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (test_id) REFERENCES email_ab_tests(id) ON DELETE CASCADE,
    INDEX ix_variants_test (test_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- EMAIL WARMUP LOGS TABLE
-- =====================================================

CREATE TABLE IF NOT EXISTS email_warmup_logs (
    id INT AUTO_INCREMENT PRIMARY KEY,
    date DATETIME(6) NOT NULL,
    emails_sent INT DEFAULT 0,
    emails_delivered INT DEFAULT 0,
    emails_bounced INT DEFAULT 0,
    emails_opened INT DEFAULT 0,
    emails_clicked INT DEFAULT 0,
    delivery_rate FLOAT DEFAULT 0.0,
    bounce_rate FLOAT DEFAULT 0.0,
    open_rate FLOAT DEFAULT 0.0,
    spam_complaints INT DEFAULT 0,
    spam_complaint_rate FLOAT DEFAULT 0.0,
    warmup_day INT NULL,
    recommended_daily_limit INT NULL,
    actual_vs_recommended FLOAT NULL,
    health_score INT NULL,
    health_status VARCHAR(20) NULL,
    health_notes TEXT NULL,
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    INDEX ix_warmup_date (date),
    INDEX ix_warmup_health (health_status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- EMAIL REPLIES TABLE (for AI analysis)
-- =====================================================

CREATE TABLE IF NOT EXISTS email_replies (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email_id INT NOT NULL,
    lead_id INT NOT NULL,
    reply_subject VARCHAR(500) NULL,
    reply_body TEXT NULL,
    reply_received_at DATETIME(6) NULL,
    intent VARCHAR(50) NULL,
    sentiment FLOAT NULL,
    confidence FLOAT NULL,
    key_points JSON NULL,
    objections JSON NULL,
    questions JSON NULL,
    recommended_action VARCHAR(50) NULL,
    urgency VARCHAR(20) NULL,
    processed BOOLEAN DEFAULT FALSE,
    processed_at DATETIME(6) NULL,
    action_taken VARCHAR(100) NULL,
    action_taken_at DATETIME(6) NULL,
    created_at DATETIME(6) DEFAULT CURRENT_TIMESTAMP(6),
    FOREIGN KEY (email_id) REFERENCES emails(id) ON DELETE CASCADE,
    FOREIGN KEY (lead_id) REFERENCES leads(id) ON DELETE CASCADE,
    INDEX ix_replies_email (email_id),
    INDEX ix_replies_lead (lead_id),
    INDEX ix_replies_intent (intent),
    INDEX ix_replies_processed (processed)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- =====================================================
-- EMAILS TABLE: Add A/B test variant tracking
-- =====================================================

ALTER TABLE emails
ADD COLUMN IF NOT EXISTS ab_test_id INT NULL;

ALTER TABLE emails
ADD COLUMN IF NOT EXISTS ab_variant_id INT NULL;

-- Add index for A/B test tracking
CREATE INDEX IF NOT EXISTS ix_emails_ab_test ON emails(ab_test_id, ab_variant_id);

-- =====================================================
-- VERIFICATION QUERIES
-- =====================================================

-- Verify leads table has new columns
-- SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS
-- WHERE TABLE_NAME = 'leads' AND COLUMN_NAME LIKE 'email_%';

-- Verify new tables exist
-- SHOW TABLES LIKE 'email_%';

-- Check table structures
-- DESCRIBE email_ab_tests;
-- DESCRIBE email_ab_test_variants;
-- DESCRIBE email_warmup_logs;
-- DESCRIBE email_replies;

SELECT 'Migration 002_email_intelligence completed successfully' AS status;
