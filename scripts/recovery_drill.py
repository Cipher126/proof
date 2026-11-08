"""Exercise the packaged Proof service with disposable, loopback-only Docker resources."""

import argparse
import json
import subprocess
import time
from contextlib import ExitStack
from datetime import datetime, timezone
from pathlib import Path
from secrets import token_hex
from uuid import uuid4

import httpx
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from benchmark_api import run as benchmark
from reconciliation_profile import HISTORY_SIZE, explain, seed_history
from smoke_demo import check, verify

CHECKED_TABLES = (
    "accounts", "transfers", "journal_transactions", "journal_entries",
    "statement_imports", "reconciliation_findings", "outbox_events",
)
ARCHIVE = "/tmp/proof-drill.dump"
RUNTIME_GRANTS = Path(__file__).resolve().parents[1] / "deploy" / "runtime_grants.sql"


def docker(*args: str, sql: str | None = None) -> str:
    result = subprocess.run(["docker", *args], input=sql, text=True, stdout=subprocess.PIPE)
    if result.returncode:
        raise subprocess.CalledProcessError(result.returncode, ["docker", args[0]])
    return result.stdout.strip()


def until(probe, timeout: float = 60) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            if probe():
                return
        except (httpx.RequestError, subprocess.CalledProcessError):
            pass
        time.sleep(0.25)
    raise RuntimeError("timed out waiting for the disposable Proof service")


def state(engine) -> dict:
    with engine.connect() as conn:
        return {
            table: tuple(conn.execute(text(
                f"SELECT count(*), md5(string_agg(to_jsonb(r)::text, '' ORDER BY r.id)) FROM {table} AS r"
            )).one())
            for table in CHECKED_TABLES
        }


def assert_immutable(engine) -> None:
    try:
        with engine.begin() as conn:
            conn.execute(text("""
                UPDATE journal_entries SET amount_minor = amount_minor + 1
                WHERE id = (SELECT id FROM journal_entries LIMIT 1)
            """))
    except DBAPIError as exc:
        check("posted journal entries are immutable" in str(exc.orig), "unexpected mutation error")
    else:
        raise RuntimeError("restored database accepted a posted entry mutation")


def drill(image: str) -> dict:
    name = f"proof-drill-{uuid4().hex[:12]}"
    database = f"{name}-db"
    password = token_hex(16)
    runtime_password = token_hex(16)
    started = datetime.now(timezone.utc).isoformat()
    with ExitStack() as cleanup:
        docker("network", "create", name)
        cleanup.callback(docker, "network", "rm", name)
        docker(
            "run", "-d", "--name", database, "--network", name,
            "-p", "127.0.0.1::5432", "-e", "POSTGRES_DB=proof",
            "-e", f"POSTGRES_PASSWORD={password}", "postgres:17-alpine",
        )
        cleanup.callback(docker, "rm", "-fv", database)
        def db_tool(*args: str, sql: str | None = None) -> str:
            flags = ["-i"] if sql is not None else []
            return docker("exec", *flags, database, args[0], "-U", "postgres", *args[1:], sql=sql)

        def server_ready() -> bool:
            return "accepting connections" in docker(
                "exec", database, "pg_isready", "-h", "127.0.0.1", "-U", "postgres", "-d", "proof",
            )

        until(server_ready)
        db_tool("psql", "-v", "ON_ERROR_STOP=1", "-d", "proof", sql=(
            f"CREATE ROLE proof_runtime LOGIN PASSWORD '{runtime_password}';"
        ))

        def migrate(db: str, revision: str) -> float:
            start = time.monotonic()
            docker("run", "--rm", "--network", name,
                   "-e", f"PROOF_DATABASE_URL=postgresql+psycopg://postgres:{password}@{database}/{db}",
                   image, ".venv/bin/alembic", "upgrade", revision)
            return round(time.monotonic() - start, 3)

        def grant(db: str) -> None:
            db_tool("psql", "-v", "ON_ERROR_STOP=1", "-d", db, sql=RUNTIME_GRANTS.read_text(encoding="utf-8"))

        def engine_for(db: str, user: str = "postgres"):
            # Docker can assign a new host port when a stopped container restarts.
            db_port = docker("port", database, "5432/tcp").rsplit(":", 1)[1]
            secret = password if user == "postgres" else runtime_password
            engine = create_engine(
                f"postgresql+psycopg://{user}:{secret}@127.0.0.1:{db_port}/{db}",
                connect_args={"connect_timeout": 5}, hide_parameters=True, pool_pre_ping=True,
            )
            cleanup.callback(engine.dispose)
            return engine

        def launch(suffix: str, db: str, environment: str) -> httpx.Client:
            api = f"{name}-{suffix}"
            docker("run", "-d", "--name", api, "--network", name, "-p", "127.0.0.1::10000",
                   "-e", "PORT=10000", "-e", f"PROOF_ENVIRONMENT={environment}",
                   "-e", f"PROOF_ADMISSION_SECRET={token_hex(32)}",
                   "-e", f"PROOF_SIMULATED_PROVIDER_SECRET={token_hex(32)}",
                   "-e", f"PROOF_DATABASE_URL=postgresql+psycopg://proof_runtime:{runtime_password}"
                   f"@{database}/{db}?application_name=proof-drill-api", image)
            cleanup.callback(docker, "rm", "-fv", api)
            port = docker("port", api, "10000/tcp").rsplit(":", 1)[1]
            client = cleanup.enter_context(httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=15))
            until(lambda: client.get("/ready").status_code == 200)
            return client

        print("Migrating to the previous revision and seeding the fictional history.", flush=True)
        migrate("proof", "0011")
        grant("proof")
        source_api = launch("source", "proof", "sandbox")
        verify(source_api)
        source = engine_for("proof")
        tenant = seed_history(source)
        before = explain(source, tenant)
        checkpoint = state(source)
        print("Taking the backup and applying the indexed migration.", flush=True)
        dump_started = time.monotonic()
        db_tool("pg_dump", "-Fc", "--no-acl", "-d", "proof", "-f", ARCHIVE)
        dump_seconds = round(time.monotonic() - dump_started, 3)
        migration_seconds = migrate("proof", "head")
        after = explain(source, tenant)
        check(state(source) == checkpoint, "the index migration changed business data")
        with source.begin() as conn:
            conn.execute(text("INSERT INTO tenants VALUES (:id, 'Post-backup canary', now())"), {"id": uuid4()})

        print("Stopping PostgreSQL, checking HTTP health, and recovering connectivity.", flush=True)
        docker("stop", database)
        outage = source_api.get("/ready")
        check(source_api.get("/health").status_code == 200, "liveness failed during a database outage")
        check(outage.status_code == 503 and outage.json()["error"]["code"] == "database_unavailable",
              "readiness did not report the database outage")
        restart_started = time.monotonic()
        docker("start", database)
        until(lambda: source_api.get("/ready").status_code == 200)
        readiness_seconds = round(time.monotonic() - restart_started, 3)

        print("Restoring into a separate database and checking the checkpoint.", flush=True)
        restore_started = time.monotonic()
        db_tool("createdb", "restored")
        db_tool("pg_restore", "--exit-on-error", "--no-owner", "--no-acl", "-d", "restored", ARCHIVE)
        restore_seconds = round(time.monotonic() - restore_started, 3)
        restored = engine_for("restored")
        runtime = engine_for("restored", "proof_runtime")
        with restored.connect() as conn:
            revision = conn.scalar(text("SELECT version_num FROM alembic_version"))
            canaries = conn.scalar(text("SELECT count(*) FROM tenants WHERE name = 'Post-backup canary'"))
            unbalanced = conn.scalar(text("""
                SELECT count(*) FROM (
                    SELECT journal_id FROM journal_entries GROUP BY journal_id HAVING sum(amount_minor) <> 0
                ) AS violations
            """))
            version = conn.scalar(text("SHOW server_version"))
        check(revision == "0011", "archive does not contain the expected prior migration revision")
        check(canaries == 0 and unbalanced == 0, "restored backup violated the checkpoint or journal balances")
        check(state(restored) == checkpoint, "restored business rows differ from the backup checkpoint")
        migrate("restored", "head")
        check(state(restored) == checkpoint, "upgrade after restore changed business data")
        grant("restored")
        assert_immutable(runtime)
        restored_api = launch("restored", "restored", "sandbox")
        verify(restored_api)
        recovery_seconds = round(time.monotonic() - restore_started, 3)

        print("Comparing hot and spread HTTP traffic with PostgreSQL lock sampling.", flush=True)
        development = launch("development", "restored", "development")
        contention = {
            layout: benchmark(str(development.base_url), 100, 8, layout, restored)
            for layout in ("hot", "spread")
        }
        return {
            "started_at": started,
            "postgresql": version,
            "reconciliation": {"synthetic_transfers": HISTORY_SIZE, "before": before, "after": after,
                               "migration_seconds_including_container_start": migration_seconds},
            "recovery": {
                "backup_seconds": dump_seconds,
                "archive_revision": revision,
                "checkpoint_table_row_counts": {table: data[0] for table, data in checkpoint.items()},
                "checkpoint_matches_restored_data": True,
                "post_backup_canary_restored": False,
                "unbalanced_journals": unbalanced,
                "posted_entry_mutation_rejected": True,
                "liveness_during_outage": 200,
                "readiness_during_outage": outage.status_code,
                "readiness_after_restart_seconds": readiness_seconds,
                "restore_seconds": restore_seconds,
                "restore_through_migration_and_http_smoke_seconds": recovery_seconds,
            },
            "contention": contention,
        }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="proof:verification")
    parser.add_argument("--output", type=Path, default=Path("artifacts/recovery/latest.json"))
    args = parser.parse_args()
    report = drill(args.image)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Recovery and performance verification passed. Report written to {args.output}.")


if __name__ == "__main__":
    main()
