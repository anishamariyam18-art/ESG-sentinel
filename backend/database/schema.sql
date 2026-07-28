-- ===========================================================
-- ESG SENTINEL DATABASE SCHEMA
-- PostgreSQL - Raw SQL (No ORM)
-- ===========================================================


-- ===========================================================
-- TABLE: users
-- ===========================================================

CREATE TABLE IF NOT EXISTS users (

    id              SERIAL PRIMARY KEY,

    name            VARCHAR(150) NOT NULL,

    email           VARCHAR(255) NOT NULL UNIQUE,

    password        VARCHAR(255) NOT NULL,

    role            VARCHAR(20)
                    NOT NULL
                    DEFAULT 'user'
                    CHECK(role IN ('user','admin')),

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);



-- ===========================================================
-- TABLE: companies
-- ===========================================================

CREATE TABLE IF NOT EXISTS companies (

    id              SERIAL PRIMARY KEY,

    name            VARCHAR(255) NOT NULL UNIQUE,

    industry        VARCHAR(150),

    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);



-- ===========================================================
-- TABLE: reports
-- ===========================================================

CREATE TABLE IF NOT EXISTS reports (

    id                  SERIAL PRIMARY KEY,


    user_id             INTEGER NOT NULL
                        REFERENCES users(id)
                        ON DELETE CASCADE,


    company_id          INTEGER NOT NULL
                        REFERENCES companies(id)
                        ON DELETE CASCADE,


    original_filename   VARCHAR(255) NOT NULL,


    stored_filename     VARCHAR(255)
                        NOT NULL
                        UNIQUE,


    file_path           VARCHAR(500)
                        NOT NULL,


    file_size           BIGINT
                        NOT NULL
                        CHECK(file_size > 0),


    status              VARCHAR(20)
                        NOT NULL
                        DEFAULT 'uploaded'
                        CHECK(
                            status IN
                            (
                                'uploaded',
                                'processing',
                                'completed',
                                'failed'
                            )
                        ),


    uploaded_at         TIMESTAMP
                        NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,


    created_at          TIMESTAMP
                        NOT NULL
                        DEFAULT CURRENT_TIMESTAMP,


    updated_at          TIMESTAMP
                        NOT NULL
                        DEFAULT CURRENT_TIMESTAMP
);





-- ===========================================================
-- TABLE: summaries
-- ===========================================================

CREATE TABLE IF NOT EXISTS summaries (

    id                  SERIAL PRIMARY KEY,


    report_id           INTEGER NOT NULL
                        REFERENCES reports(id)
                        ON DELETE CASCADE,


    summary             TEXT NOT NULL,


    environment_score   NUMERIC(5,2)
                        CHECK(
                            environment_score BETWEEN 0 AND 100
                        ),


    social_score        NUMERIC(5,2)
                        CHECK(
                            social_score BETWEEN 0 AND 100
                        ),


    governance_score    NUMERIC(5,2)
                        CHECK(
                            governance_score BETWEEN 0 AND 100
                        ),


    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);






-- ===========================================================
-- TABLE: claims
-- ===========================================================

CREATE TABLE IF NOT EXISTS claims (

    id              SERIAL PRIMARY KEY,


    report_id       INTEGER NOT NULL
                    REFERENCES reports(id)
                    ON DELETE CASCADE,


    claim_text      TEXT NOT NULL,


    category        VARCHAR(50)
                    CHECK(
                        category IN
                        (
                            'environment',
                            'social',
                            'governance',
                            'general'
                        )
                    ),


    page_number     INTEGER
                    CHECK(page_number > 0),


    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);







-- ===========================================================
-- TABLE: evidences
-- ===========================================================

CREATE TABLE IF NOT EXISTS evidences (

    id                  SERIAL PRIMARY KEY,


    claim_id            INTEGER NOT NULL
                        REFERENCES claims(id)
                        ON DELETE CASCADE,


    source_name         VARCHAR(255) NOT NULL,


    source_url          VARCHAR(500),


    evidence_text       TEXT NOT NULL,


    confidence_score    NUMERIC(5,2)
                        CHECK(
                            confidence_score BETWEEN 0 AND 100
                        ),


    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);







-- ===========================================================
-- TABLE: verifications
-- ===========================================================

CREATE TABLE IF NOT EXISTS verifications (

    id                      SERIAL PRIMARY KEY,


    claim_id                INTEGER NOT NULL
                            REFERENCES claims(id)
                            ON DELETE CASCADE,


    verification_status     VARCHAR(20)
                            NOT NULL
                            CHECK(
                                verification_status IN
                                (
                                    'verified',
                                    'unverified',
                                    'false',
                                    'misleading'
                                )
                            ),


    confidence              NUMERIC(5,2)
                            CHECK(
                                confidence BETWEEN 0 AND 100
                            ),


    reason                  TEXT,


    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);









-- ===========================================================
-- TABLE: greenwashing_results
-- ===========================================================

CREATE TABLE IF NOT EXISTS greenwashing_results (

    id              SERIAL PRIMARY KEY,


    report_id       INTEGER NOT NULL
                    REFERENCES reports(id)
                    ON DELETE CASCADE,


    risk_level      VARCHAR(20)
                    NOT NULL
                    CHECK(
                        risk_level IN
                        (
                            'low',
                            'medium',
                            'high',
                            'critical'
                        )
                    ),


    score           NUMERIC(5,2)
                    NOT NULL
                    CHECK(
                        score BETWEEN 0 AND 100
                    ),


    explanation     TEXT,


    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);








-- ===========================================================
-- TABLE: trust_scores
-- ===========================================================

CREATE TABLE IF NOT EXISTS trust_scores (

    id                  SERIAL PRIMARY KEY,


    report_id           INTEGER NOT NULL
                        REFERENCES reports(id)
                        ON DELETE CASCADE,


    environment_score   NUMERIC(5,2)
                        CHECK(
                            environment_score BETWEEN 0 AND 100
                        ),


    social_score        NUMERIC(5,2)
                        CHECK(
                            social_score BETWEEN 0 AND 100
                        ),


    governance_score    NUMERIC(5,2)
                        CHECK(
                            governance_score BETWEEN 0 AND 100
                        ),


    overall_score       NUMERIC(5,2)
                        NOT NULL
                        CHECK(
                            overall_score BETWEEN 0 AND 100
                        ),


    generated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,


    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,


    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);








-- ===========================================================
-- INDEXES
-- ===========================================================


CREATE INDEX IF NOT EXISTS idx_users_email
ON users(email);



CREATE INDEX IF NOT EXISTS idx_reports_user_id
ON reports(user_id);



CREATE INDEX IF NOT EXISTS idx_reports_company_id
ON reports(company_id);



CREATE INDEX IF NOT EXISTS idx_reports_status
ON reports(status);



CREATE INDEX IF NOT EXISTS idx_reports_uploaded_at
ON reports(uploaded_at);



CREATE INDEX IF NOT EXISTS idx_companies_name
ON companies(name);



CREATE INDEX IF NOT EXISTS idx_summaries_report_id
ON summaries(report_id);



CREATE INDEX IF NOT EXISTS idx_claims_report_id
ON claims(report_id);



CREATE INDEX IF NOT EXISTS idx_evidences_claim_id
ON evidences(claim_id);



CREATE INDEX IF NOT EXISTS idx_verifications_claim_id
ON verifications(claim_id);



CREATE INDEX IF NOT EXISTS idx_verifications_status
ON verifications(verification_status);



CREATE INDEX IF NOT EXISTS idx_greenwashing_report_id
ON greenwashing_results(report_id);



CREATE INDEX IF NOT EXISTS idx_trust_scores_report_id
ON trust_scores(report_id);