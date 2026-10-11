# Python backend rebuild

First milestone of the n8n-free replacement. FastAPI handles authenticated workspace commands, PostgreSQL holds durable jobs, and separate Python workers execute research. This package does not import the old API or n8n. The existing public-fetch guard was carried forward as a standalone utility to retain robots, DNS pinning and private-network protections.

Implemented: password login, hashed expiring bearer sessions, login throttling, workspace roles, product/ICP upserts, leads, idempotent research requests, job history and explicit failed-job retry. Forced PostgreSQL row-level policies protect catalog, lead and job records. The API uses a restricted role; the trusted worker can process jobs across workspaces but cannot read account/password/session tables. Migrations and local account provisioning use a separate administrative connection.

Workers use `FOR UPDATE SKIP LOCKED`, renewable leases and persisted checkpoints. Transient model errors have bounded backoff; configuration and citation failures stop immediately. Expired workers cannot save results. Provider requests may repeat after uncertain transport failures; exactly-once provider billing is not promised. This milestone has no sending executor.

The first research handler reads one public company homepage and validates structured xKiro findings against exact quotes. It stops at `NEEDS_REVIEW`. Discovery, deeper pages, industry/people enrichment, contact resolution, scoring, matching, drafts, approval, SMTP, dashboard integration and migration remain subsequent milestones.

## Local setup

Use the separate `compose.backend.yml` project and volume. Copy `backend/.env.example` to an ignored `.env.backend-local` and set three distinct URL-safe hexadecimal passwords of at least 24 characters. The current session already created that private file. No existing DEV data, accounts or n8n keys were copied.

```powershell
docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml up --build -d backend-api backend-worker
```

API mapping: `127.0.0.1:8020`; OpenAPI: `/docs`. Bootstrap the first administrator on the empty database through the migration service. The password is entered at a hidden prompt:

```powershell
docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml run --rm backend-migrate python -m marketing_backend.cli bootstrap --email your-email@example.com --workspace LorrySystem
```

Bootstrap refuses a database that already has users. Subsequent local provisioning uses `add-member --role OPERATOR --workspace LorrySystem` through the same administrative service. Web invitations and account recovery are future work.

Configure `BACKEND_MODEL_API_KEY` privately when ready for live tests. Missing keys stop before fetching. New configuration is independent of n8n credentials. Tests use mocked providers.

## Verification

Tests refuse any database except `marketing_rebuild_test` with `APP_ENV=test`. Create it once inside the isolated rebuild PostgreSQL:

```powershell
docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml exec backend-db createdb -U marketing_rebuild marketing_rebuild_test
docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml --profile test run --rm --build backend-test
```

Ten integration tests cover authentication, roles, database isolation, worker permissions, concurrent claims, idempotency, lease expiry, bounded retries, checkpoint recovery, provider contracts, configuration stops and citation/private-target rejection.

A separate smoke test exercises the running API and worker with their actual restricted roles. It creates and removes only its explicitly identified synthetic fixtures. Run it with the model key empty:

```powershell
docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml --profile test run --rm --build backend-smoke
```

Both suites passed locally. Health works inside Docker. Windows host localhost forwarding was unavailable despite the port mapping; browser access needs Docker Desktop networking verification.

## Subsequent milestones

1. Native discovery, bounded multi-page research, industry and sourced people/contacts.
2. Contact resolution, evidence-gated scoring, matching and drafting; provider budgets and usage.
3. Approval snapshots, stale-context checks and separate safe sending.
4. Dashboard integration, controlled data/credential migration and executor cutover.

This is a local backend foundation, not a complete replacement release or production cutover.
