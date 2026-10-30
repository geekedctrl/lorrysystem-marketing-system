# Python backend rebuild

Native backend of the n8n-free replacement. FastAPI handles authenticated workspace commands, PostgreSQL holds durable jobs, and separate Python workers execute product setup, discovery, deeper research, contact search, scoring, matching and outreach drafting. This package does not import the old API or n8n. The existing public-fetch guard was carried forward as a standalone utility to retain robots, DNS pinning and private-network protections.

Implemented: password login, hashed expiring bearer sessions, login throttling, workspace roles, product/ICP upserts, leads, idempotent research requests, job history and explicit failed-job retry. Forced PostgreSQL row-level policies protect catalog, lead and job records. The API uses a restricted role; the trusted worker can process jobs across workspaces but cannot read account/password/session tables. Migrations and local account provisioning use a separate administrative connection.

Workers use `FOR UPDATE SKIP LOCKED`, renewable leases and persisted checkpoints. Transient model errors have bounded backoff; configuration and citation failures stop immediately. Expired workers cannot save results. Provider requests may repeat after uncertain transport failures; exactly-once provider billing is not promised. Controlled sending now uses a separate human authorization and transactional outbox; installation alone does not authorize delivery.

Model calls use xKiro's JSON response mode and validate every result before use. Discovery reports malformed JSON, truncation, incomplete responses and schema mismatch separately, and permits one additional budget-reserved correction call for an invalid company assessment. Research bounds model-returned contacts to five and drops individual unsupported facts or contacts with an explicit coverage note, preserving other verified evidence. Other stage schema failures are reported as `MODEL_OUTPUT_SCHEMA_INVALID`. Website fetch failures are independent and may require a later reassessment.

The shared pipeline advances eligible leads to a draft `PENDING_APPROVAL`. Evidence/contact/qualification gaps stop with explicit review reasons. Administrator/Reviewer approval is separate and never sends. Manual homepage-only research remains available. See [native preparation workers](../docs/native-preparation-workers.md) for policies, APIs, reservations and remaining cutover work.

## Local setup

Use the separate `compose.backend.yml` project and volume. The root ignored `.env` is the single local configuration file for all stacks. Keep the three native database passwords distinct and at least 24 URL-safe hexadecimal characters; do not replace existing values when adding settings. No existing DEV data or accounts are copied into the local database.

```powershell
docker compose --env-file .env -p marketing-rebuild -f compose.backend.yml up --build -d backend-api backend-worker
```

API mapping: `127.0.0.1:8020`; native dashboard mapping: `127.0.0.1:8093` when `NATIVE_DASHBOARD_HOST_PORT=8093`; OpenAPI: `/docs`. Bootstrap the first administrator on the empty database through the migration service. The password is entered at a hidden prompt:

```powershell
docker compose --env-file .env -p marketing-rebuild -f compose.backend.yml run --rm backend-migrate python -m marketing_backend.cli bootstrap --email your-email@example.com --workspace LorrySystem
```

Bootstrap refuses a database that already has users. Subsequent local provisioning uses `add-member --role OPERATOR --workspace LorrySystem` through the same administrative service. Web invitations and account recovery are future work.

Platform operators configure `BACKEND_MODEL_API_KEY`, `BACKEND_BRAVE_SEARCH_API_KEY` and confirmed provider input/output/search rates privately when ready for authorized live tests. Missing keys/rates stop before provider calls. The configurable monthly allowance covers conservative API reservations in this backend, not hosting or other systems. New configuration is independent of n8n credentials. Product teams do not configure providers. Tests use mocked providers.

## Verification

Tests refuse any database except `marketing_rebuild_test` with `APP_ENV=test`. Create it once inside the isolated rebuild PostgreSQL:

```powershell
docker compose --env-file .env -p marketing-rebuild -f compose.backend.yml exec backend-db createdb -U marketing_rebuild marketing_rebuild_test
docker compose --env-file .env -p marketing-rebuild -f compose.backend.yml --profile test run --rm --build backend-test
```

Fifty-six PostgreSQL-backed tests cover authentication, roles, database isolation, worker permissions, concurrent claims, idempotency, lease expiry, bounded retries, checkpoint recovery, provider contracts, reservations, configuration stops, citation/private-target rejection, all native stages, contact resolution, stale approvals and six synthetic companies across two unrelated catalogs. Regressions verify that excess model-returned contacts are capped, unsupported individual findings are omitted without blocking valid research, and keyed scoring/citation aliases from compatible models are safely normalized to the rubric contract.

A separate smoke test exercises the running API and worker with their actual restricted roles. It creates and removes only its explicitly identified synthetic fixtures. Run it with the model key empty:

```powershell
docker compose --env-file .env -p marketing-rebuild -f compose.backend.yml --profile test run --rm --build backend-smoke
```

Both suites passed locally. Health works inside Docker. Windows host localhost forwarding was unavailable despite the port mapping; browser access needs Docker Desktop networking verification.

## Subsequent milestones

The implementation order, acceptance criteria and cutover boundaries are defined in the [native worker migration plan](../docs/native-worker-migration-plan.md).

1. Real-provider coverage, score and draft calibration with an approved allowance; richer evidence/contact resolution and targeting controls.
2. Encrypted in-app provider connections and rotation, plus dashboard integration for native product/setup/review/operations APIs.
3. Validate the implemented native dashboard sending flow with a controlled test inbox only after explicit authorization.
4. Controlled data/account/credential migration, executor ownership and rollback validation before disabling n8n.

This is a local backend foundation, not a complete replacement release or production cutover.

Migration control runs from the administrative migration service with a read-only legacy URL:
`python -m marketing_backend.cli migration export|dry-run|apply|reconcile|final-delta`.
Apply copies compatible workspace identities and records `legacy_identity_map`; reconciliation differences keep Python activation blocked.
Set `MIGRATION_EXPORT_PATH` for `export` to create an immutable JSON review artifact; the command refuses to overwrite an existing export.

## Native frontend support update

BE-01–BE-06 backend support is implemented and tested locally: typed responses/current-user capabilities, lead detail/keyset pagination, immutable human draft revisions with a different reviewer, soft catalog lifecycle and persistent context versions. Product setup keeps explicit partial-save semantics. The worker loop now checks due discovery continuously. Migrations006/007 belong to this independent database.

The separate `compose.native-integration.yml` runs actual native API/workers/PostgreSQL with the frontend owner's checkout and guarded synthetic providers. Thirty-seven database tests, real HTTP/BFF two-product acceptance, actual headless Edge preparation/approval and restricted API revision/lifecycle checks pass. See [integration setup and frontend adaptations](../docs/native-frontend-backend-support.md). New BFF endpoint adapters remain frontend work. Windows host forwarding has a tested local gateway fallback; no DEV/n8n cutover or real sending/provider test is implied.


### Discovery review update — 11 October 2026

Discovery now waits for explicit user acceptance before lead creation/research. See [native lead discovery](../docs/native-lead-discovery.md) for candidate APIs, native UI/BFF adapters, migration008, worker libraries/limits, local acceptance and coordinated release requirements. Earlier automatic discovery acceptance guidance is superseded.

Native controlled sending is implemented in migration009 with encrypted workspace sender connections, immutable delivery snapshots, separate send approval, a transactional outbox, bounded known-failure retries and fail-closed uncertain handoffs. See [native controlled sending](../docs/native-sending.md). Synthetic transport tests only; no DEV executor ownership or outbound message is enabled.

## Independent worker pools

The worker command now selects exactly one pool with `--pool` (or `WORKER_POOL`).
The seven stage pools are SETUP, DISCOVERY, RESEARCH, CONTACT_SEARCH, SCORING,
MATCHING and DRAFTING. EMAIL, SOCIAL and MESSAGING are separate delivery pools;
SCHEDULER alone handles due discovery and expired job/delivery recovery. The
existing `backend-worker` Compose service is the RESEARCH pool. Every pool serves
all product lines; line concurrency and provider controls remain database scoped.

Merge `compose.worker-pools.yml` with `compose.backend.yml` to start the full
pipeline. Start the API, backend-worker and the backend-setup, backend-discovery,
backend-contacts, backend-scoring, backend-matching, backend-content, backend-email,
backend-social, backend-messaging and backend-scheduler services. The base Compose
file alone starts only the research pool. It is not a full pipeline deployment.
Each pool has an independent restart policy and a process/database readiness
probe. `WORKER_<POOL>_CONCURRENCY` configures 1–8 local execution slots; the scheduler
requires one. Database line limits still bound concurrent work across replicas.

Social currently routes approved LINKEDIN assets. MESSAGING provides an adapter
boundary and synthetic acceptance fixtures; the existing content producer does
not generate messaging assets. There are no live social or messaging adapters.
The synthetic adapters require explicit `DELIVERY_ADAPTER_MODE=synthetic` and a
test/acceptance APP_ENV. Normal runtime fails closed as CHANNEL_NOT_CONFIGURED.
Email retains verified sender, suppression, exact approval, separate send approval
and uncertain handoff checks. A timed-out delivery is never automatically resent.

`POST /workspaces/{wid}/channel-deliveries` prepares an outbox record for an
explicitly approved versioned product-line social/message snapshot. The existing
approve-send endpoint authorizes execution separately. Delivery events are exposed
through `GET /workspaces/{wid}/deliveries/{id}/events`; sensitive content is excluded.
Migration 017 preserves existing email snapshots/decisions, adds immutable channel
routing and trace identity, and introduces append-only delivery diagnostics. Runtime
roles cannot edit or delete that history. Downgrade requires a forward recovery plan.

For local synthetic runtime validation also merge `compose.worker-day2-test.yml`.
This clears provider/sender credentials and makes backend-smoke exercise a normal
API research task plus quarantine before execution in all seven stage pools. The
backend-test suite separately starts restricted subprocesses with guarded fake
providers, fake channels, concurrent claims, restart recovery and a synthetic query
strategy canary. No live provider or outbound-send test is required.

Product-line settings accept discovery_query_strategy=baseline (icp-queries.1) or
explicit canary opt-in official (icp-queries.2). Both produce the same candidate
contract. Roll back by selecting baseline for new work. A setting edit creates a
new context and invalidates in-flight old work; historical artifacts and human
acceptance/approval decisions are retained. Synthetic canary results are not proof
of real-world provider quality or paid usage.
