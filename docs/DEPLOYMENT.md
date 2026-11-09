# Deploy Proof

Use an isolated PostgreSQL database for the fictional public sandbox. Keep named-operator workloads in a separate deployment.

## Free portfolio demo on Render and Neon

The [Render Blueprint](../render.yaml) defines one Free Docker web service. It binds to Render's `PORT`, checks `/ready`, and generates distinct secrets for admission and simulated provider signatures. Neon supplies the database. The public demo runs the dashboard and API. The webhook worker and retention loop are separate processes in the Compose deployment.

1. Create a dedicated Neon Free project in a region close to the Render service. Use the migration owner's **direct** connection with TLS. Use `postgresql+psycopg://` for Alembic and the API and `postgresql://` for `psql`. Keep the migration connection in a private local environment.
2. Run `uv sync --frozen`, then run `uv run alembic upgrade head` with `PROOF_DATABASE_URL` set to the migration owner's connection. Create a `proof_runtime` login using SQL and a generated password stored in a secret manager. Apply [runtime grants](../deploy/runtime_grants.sql) with `psql -v ON_ERROR_STOP=1 -f deploy/runtime_grants.sql` as the migration owner. Create the login via SQL to avoid Neon's elevated role membership for console-created roles.
3. Connect the Git repository in Render and create a Blueprint from `render.yaml`. Supply the TLS-enabled `proof_runtime` connection as `PROOF_DATABASE_URL`. Use the Free plan and confirm the region and allowances before provisioning.
4. Wait for the first deployment and run `uv run python scripts/smoke_demo.py --base-url https://YOUR-SERVICE.onrender.com`. Record the deployed Git commit, migration revision, public URL, and smoke result. Confirm that a request without credentials returns 401 on a tenant route and that `/metrics` returns 404.
5. For updates, take a backup, apply the migration and runtime grants, then manually deploy the reviewed commit. Render Free runs without a pre-deploy hook. For the additive index in 0012, the prior application can keep running against the migrated database. Deploy the previous image if the application rollout fails and keep the compatible index in place.

Render Free sleeps when idle, and Neon Free can scale to zero. Budget for the first request to take longer and check both providers' quotas. The default proxy trust setting stays restricted to loopback. With a shared proxy address, Proof applies the same conservative admission bucket to visitors behind that address. Monitor demo 429 responses and run the retention command from a trusted host when the dedicated database approaches its scenario cap.

[Render Free limitations](https://render.com/docs/free) · [Render Blueprint specification](https://render.com/docs/blueprint-spec) · [Neon connection configuration](https://neon.com/docs/connect/connect-from-any-app) · [Neon roles](https://neon.com/docs/manage/roles) · [Neon plans](https://neon.com/docs/introduction/plans)

## Configure the host

Supply the following values through the host's secret configuration or a private environment file stored outside the source tree.

- `PROOF_MIGRATION_DATABASE_URL` uses the migration owner.
- `PROOF_RUNTIME_DATABASE_URL` uses a distinct login with schema usage and table read/write grants. Do not grant table ownership, schema creation, or trigger administration. Review the exact grants after migration.
- `PROOF_ADMISSION_SECRET` is a random shared secret for the rate limiter.
- `PROOF_SIMULATED_PROVIDER_SECRET` is a separate random value of at least 32 characters.
- `PROOF_TRUSTED_PROXY_IPS` lists only the proxy addresses observed by Uvicorn. Configure the proxy to overwrite forwarded client headers. Never use a wildcard.

Run the migration service before starting the API. The migration owner must grant the runtime login access to the resulting tables and default privileges for later migrations.

```bash
docker compose -f compose.hosted.yaml build api
docker compose -f compose.hosted.yaml run --rm migrate
docker compose -f compose.hosted.yaml up -d --no-build
```

Route TLS traffic to the loopback listener on port 18080. Limit request sizes and connection rates at the proxy. Keep monitoring endpoints private. Verify `/ready`, then create and resolve a fictional incident through the browser.

Use `--profile retain` on the dedicated sandbox after taking a backup and reviewing `python -m proof.maintenance` dry-run output with the migration-owner connection. The worker prunes anonymous demo tenants more than one day after credential expiry. It leaves tenants with named credentials alone.

## Operate named credentials

Set `PROOF_ENVIRONMENT=operations` for a dedicated operator deployment. Run the runtime grants with `psql -v ON_ERROR_STOP=1 -v proof_operations=on -f deploy/runtime_grants.sql` as the migration owner. This gives the runtime read-only access to operator credentials. Run the administrative CLI with a separate trusted connection that can manage credentials.

```bash
python -m proof.admin tenant "Fictional operations"
python -m proof.admin issue TENANT_UUID "Settlement operator" operator --hours 24
python -m proof.admin revoke CREDENTIAL_UUID
```

Issue outputs the bearer token once. Store it securely. Integrators can create and transition payments, operators manage journals and settlements, auditors read records, and provider keys can submit signed evidence. The signature input is the UTF-8 prefix `v1.<timestamp>.<tenant UUID>.<event ID>.` followed by the original request bytes. Use HMAC-SHA256 and a hex digest.

## Observe and deliver

For local monitoring, start `docker compose --profile observe up -d` and open Grafana on port 13001. Set `PROOF_OTLP_TRACES_ENDPOINT` to a reachable HTTP trace endpoint when running a collector. For external delivery, enable the worker profile and set `PROOF_OUTBOX_URL` to an approved HTTPS receiver. The receiver must deduplicate the stable `Idempotency-Key`.
