# Python backend rebuild

Native backend of the n8n-free replacement. FastAPI handles authenticated workspace commands, PostgreSQL holds durable jobs, and separate Python workers execute product setup, discovery, deeper research, contact search, scoring, matching and outreach drafting. This package does not import the old API or n8n. The existing public-fetch guard was carried forward as a standalone utility to retain robots, DNS pinning and private-network protections.

Implemented: password login, hashed expiring bearer sessions, login throttling, workspace roles, product/ICP upserts, leads, idempotent research requests, job history and explicit failed-job retry. Forced PostgreSQL row-level policies protect catalog, lead and job records. The API uses a restricted role; the trusted worker can process jobs across workspaces but cannot read account/password/session tables. Migrations and local account provisioning use a separate administrative connection.

Workers use `FOR UPDATE SKIP LOCKED`, renewable leases and persisted checkpoints. Transient model errors have bounded backoff; configuration and citation failures stop immediately. Expired workers cannot save results. Provider requests may repeat after uncertain transport failures; exactly-once provider billing is not promised. This milestone has no sending executor.

The shared pipeline advances eligible leads to a draft `PENDING_APPROVAL`. Evidence/contact/qualification gaps stop with explicit review reasons. Administrator/Reviewer approval is separate and never sends. Manual homepage-only research remains available. See [native preparation workers](../docs/native-preparation-workers.md) for policies, APIs, reservations and remaining cutover work.

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

Platform operators configure `BACKEND_MODEL_API_KEY`, `BACKEND_BRAVE_SEARCH_API_KEY` and confirmed provider input/output/search rates privately when ready for authorized live tests. Missing keys/rates stop before provider calls. The configurable monthly allowance covers conservative API reservations in this backend, not hosting or other systems. New configuration is independent of n8n credentials. Product teams do not configure providers. Tests use mocked providers.

## Verification

Tests refuse any database except `marketing_rebuild_test` with `APP_ENV=test`. Create it once inside the isolated rebuild PostgreSQL:

```powershell
docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml exec backend-db createdb -U marketing_rebuild marketing_rebuild_test
docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml --profile test run --rm --build backend-test
```

Thirty integration tests cover authentication, roles, database isolation, worker permissions, concurrent claims, idempotency, lease expiry, bounded retries, checkpoint recovery, provider contracts, reservations, configuration stops, citation/private-target rejection, all native stages, contact resolution, stale approvals and six synthetic companies across two unrelated catalogs.

A separate smoke test exercises the running API and worker with their actual restricted roles. It creates and removes only its explicitly identified synthetic fixtures. Run it with the model key empty:

```powershell
docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml --profile test run --rm --build backend-smoke
```

Both suites passed locally. Health works inside Docker. Windows host localhost forwarding was unavailable despite the port mapping; browser access needs Docker Desktop networking verification.

## Subsequent milestones

The implementation order, acceptance criteria and cutover boundaries are defined in the [native worker migration plan](../docs/native-worker-migration-plan.md).

1. Real-provider coverage, score and draft calibration with an approved allowance; richer evidence/contact resolution and targeting controls.
2. Encrypted in-app provider connections and rotation, plus dashboard integration for native product/setup/review/operations APIs.
3. Separate safe sending, preserving the legacy SMTP approval/suppression/uncertain-handoff safeguards.
4. Controlled data/account/credential migration, executor ownership and rollback validation before disabling n8n.

This is a local backend foundation, not a complete replacement release or production cutover.
