-- Run as the migration owner in the dedicated Proof database, after creating
-- the proof_runtime login and applying migrations.
GRANT USAGE ON SCHEMA public TO proof_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO proof_runtime;
REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM proof_runtime;
