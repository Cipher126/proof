# Deploy Proof

The local Compose stack is for fictional scenarios. A hosted instance needs a Docker host, an isolated PostgreSQL database, and a reverse proxy with TLS. Use a dedicated database for the public sandbox. Keep named-operator workloads in a separate deployment.

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

Set `PROOF_ENVIRONMENT=operations` for a dedicated operator deployment. Provision a tenant and key with the administrative CLI over a trusted connection:

```bash
python -m proof.admin tenant "Fictional operations"
python -m proof.admin issue TENANT_UUID "Settlement operator" operator --hours 24
python -m proof.admin revoke CREDENTIAL_UUID
```

Issue outputs the bearer token once. Store it securely. Integrators can create and transition payments, operators manage journals and settlements, auditors read records, and provider keys can submit signed evidence. The signature input is the UTF-8 prefix `v1.<timestamp>.<tenant UUID>.<event ID>.` followed by the original request bytes. Use HMAC-SHA256 and a hex digest.

## Observe and deliver

For local monitoring, start `docker compose --profile observe up -d` and open Grafana on port 13001. Set `PROOF_OTLP_TRACES_ENDPOINT` to a reachable HTTP trace endpoint when running a collector. For external delivery, enable the worker profile and set `PROOF_OUTBOX_URL` to an approved HTTPS receiver. The receiver must deduplicate the stable `Idempotency-Key`.
