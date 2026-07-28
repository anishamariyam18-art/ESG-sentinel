-- ===========================================================
-- SEED DATA
-- ESG Sentinel - Minimal Development Seed
-- Passwords are plain placeholders (NOT hashed) for dev only
-- ===========================================================

BEGIN;

INSERT INTO users (name, email, password, role)
VALUES
    ('ESG Admin', 'admin@esgsentinel.com', 'placeholder_admin_password', 'admin'),
    ('Test User', 'user@esgsentinel.com', 'placeholder_user_password', 'user')
ON CONFLICT (email) DO NOTHING;

COMMIT;