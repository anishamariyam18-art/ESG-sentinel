-- ===========================================================
-- MIGRATION 001: INITIAL SCHEMA
-- ESG Sentinel - PostgreSQL
-- Executable top to bottom. Idempotent via IF NOT EXISTS.
-- ===========================================================

BEGIN;

-- ===========================================================
-- users
-- ===========================================================
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(150) NOT NULL,
    email           VARCHAR(255) NOT NULL UNIQUE,
    password        VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================
-- reports
-- ===========================================================
CREATE TABLE IF NOT EXISTS reports (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    original_filename   VARCHAR(255) NOT NULL,
    stored_filename     VARCHAR(255) NOT NULL UNIQUE,
    file_path           VARCHAR(500) NOT NULL,
    file_size           BIGINT NOT NULL CHECK (file_size > 0),
    status              VARCHAR(20) NOT NULL DEFAULT 'uploaded'
                            CHECK (status IN ('uploaded', 'processing', 'completed', 'failed')),
    uploaded_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================
-- summaries
-- ===========================================================
CREATE TABLE IF NOT EXISTS summaries (
    id                  SERIAL PRIMARY KEY,
    report_id           INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    summary             TEXT NOT NULL,
    environment_score   NUMERIC(5,2) CHECK (environment_score >= 0 AND environment_score <= 100),
    social_score        NUMERIC(5,2) CHECK (social_score >= 0 AND social_score <= 100),
    governance_score    NUMERIC(5,2) CHECK (governance_score >= 0 AND governance_score <= 100),
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================
-- claims
-- ===========================================================
CREATE TABLE IF NOT EXISTS claims (
    id              SERIAL PRIMARY KEY,
    report_id       INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    claim_text      TEXT NOT NULL,
    category        VARCHAR(50) CHECK (category IN ('environment', 'social', 'governance', 'general')),
    page_number     INTEGER CHECK (page_number > 0),
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================
-- evidences
-- ===========================================================
CREATE TABLE IF NOT EXISTS evidences (
    id                  SERIAL PRIMARY KEY,
    claim_id            INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    source_name         VARCHAR(255) NOT NULL,
    source_url          VARCHAR(500),
    evidence_text       TEXT NOT NULL,
    confidence_score    NUMERIC(5,2) CHECK (confidence_score >= 0 AND confidence_score <= 100),
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================
-- verifications
-- ===========================================================
CREATE TABLE IF NOT EXISTS verifications (
    id                      SERIAL PRIMARY KEY,
    claim_id                INTEGER NOT NULL REFERENCES claims(id) ON DELETE CASCADE,
    verification_status     VARCHAR(20) NOT NULL
                                CHECK (verification_status IN ('verified', 'unverified', 'false', 'misleading')),
    confidence              NUMERIC(5,2) CHECK (confidence >= 0 AND confidence <= 100),
    reason                  TEXT,
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================
-- greenwashing_results
-- ===========================================================
CREATE TABLE IF NOT EXISTS greenwashing_results (
    id              SERIAL PRIMARY KEY,
    report_id       INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    risk_level      VARCHAR(20) NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
    score           NUMERIC(5,2) NOT NULL CHECK (score >= 0 AND score <= 100),
    explanation     TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================
-- trust_scores
-- ===========================================================
CREATE TABLE IF NOT EXISTS trust_scores (
    id                  SERIAL PRIMARY KEY,
    report_id           INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
    environment_score   NUMERIC(5,2) CHECK (environment_score >= 0 AND environment_score <= 100),
    social_score        NUMERIC(5,2) CHECK (social_score >= 0 AND social_score <= 100),
    governance_score    NUMERIC(5,2) CHECK (governance_score >= 0 AND governance_score <= 100),
    overall_score       NUMERIC(5,2) NOT NULL CHECK (overall_score >= 0 AND overall_score <= 100),
    generated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================
-- INDEXES
-- ===========================================================
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

CREATE INDEX IF NOT EXISTS idx_reports_user_id ON reports(user_id);
CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);

CREATE INDEX IF NOT EXISTS idx_summaries_report_id ON summaries(report_id);

CREATE INDEX IF NOT EXISTS idx_claims_report_id ON claims(report_id);

CREATE INDEX IF NOT EXISTS idx_evidences_claim_id ON evidences(claim_id);

CREATE INDEX IF NOT EXISTS idx_verifications_claim_id ON verifications(claim_id);
CREATE INDEX IF NOT EXISTS idx_verifications_status ON verifications(verification_status);

CREATE INDEX IF NOT EXISTS idx_greenwashing_report_id ON greenwashing_results(report_id);

CREATE INDEX IF NOT EXISTS idx_trust_scores_report_id ON trust_scores(report_id);

COMMIT;