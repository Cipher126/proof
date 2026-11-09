-- Run as the migration owner in the dedicated Proof database, after creating
-- the proof_runtime login and applying migrations.
-- With psql, pass -v proof_operations=on only for the operations database.
BEGIN;
GRANT USAGE ON SCHEMA public TO proof_runtime;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO proof_runtime;
REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM proof_runtime;
REVOKE ALL PRIVILEGES ON operator_credentials FROM proof_runtime;
\if :{?proof_operations}
  \if :proof_operations
    GRANT SELECT ON operator_credentials TO proof_runtime;
  \endif
\endif
COMMIT;
