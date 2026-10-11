# Native frontend backend support

Implemented locally on 11 October 2026 on `rebuild/native-frontend-support`, based on merged native-worker PR #29. This implements backend handoff items BE-01 through BE-06. The frontend implementation remains in its owner's `geekedctrl/redesign-frontend` checkout; no frontend-owned bridge, templates, JavaScript or tests were modified.

## Completed slices

| Item | Implemented / verified |
| --- | --- |
| BE-01 Connectivity | Independent local integration Compose stack, internal `http://backend-api:8000` URL and localhost frontend. Actual server login/workspace reads pass. Optional loopback bridge restores Windows browser access where Docker Desktop forwarding fails. |
| BE-02 Actual acceptance | Disposable PostgreSQL, native restricted API/worker roles, two unrelated products, all four roles, private synthetic accounts, deterministic external evidence/providers, HTTP acceptance and actual headless browser journey. |
| BE-03 Contracts/capabilities | Typed public responses for auth/workspaces/catalog/leads/jobs/preparation/approvals/operations, progressive stage result types, `/auth/me`, refreshed OpenAPI and normalized synthetic examples. |
| BE-04 Lead access | Direct single-lead detail, stable newest-first legacy list, additive keyset pagination, literal company search, current-status filter and filtered total. |
| BE-05 Revisions | Source-backed human draft edits after requested changes, reviewer-note retention, optimistic version/current-context checks, idempotency, new immutable approval/run and separate reviewer. |
| BE-06 Catalog | Soft deactivation/reactivation, inactive item listing, persistent context versions, historical snapshot retention, explicit partial setup semantics and safe no-op upsert retries. |

Actual integration also found and fixed a worker-loop gap: due discovery scheduling now runs in the idle/active worker loop instead of relying on a provider failure path. A regression test and actual automatic discovery verify this behavior.

## Local integration setup

The frontend owner must provide a checkout containing `dashboard/app/native.py`, `native.html`, `native.js` and `native.css`. From the backend repository root:

```powershell
python backend/scripts/setup_native_integration.py --frontend-path 'C:/path/to/frontend-checkout'
docker compose --env-file .env.native-integration-local -p native-acceptance -f compose.native-integration.yml up --build -d native-frontend native-worker
docker compose --env-file .env.native-integration-local -p native-acceptance -f compose.native-integration.yml --profile test run --rm --no-deps --build native-check
```

The configuration helper generates three distinct random database passwords in an ignored local file and refuses to overwrite it. The bootstrap command creates accounts only in the dedicated `marketing_native_acceptance` database, guarded by `APP_ENV=native-acceptance`. Rerunning bootstrap retains its existing private manifest; it never adds fixtures to application workspaces.

| Service / network | Address or resource |
| --- | --- |
| Frontend browser mapping | `http://127.0.0.1:8094` |
| Frontend server → native API | `http://backend-api:8000` on `native-acceptance_default` |
| Database | `native-db:5432/marketing_native_acceptance`; no host port |
| Native workers | Real worker loop/leases/transitions under `backend_worker`; synthetic provider/evidence adapters only in the guarded test launcher |
| Private fixture accounts | `/fixtures/accounts.json` in `native-acceptance_native-acceptance-fixtures`, readable by the backend test user |
| Data volume | `native-acceptance_native-acceptance-data` |

No model/search keys are supplied to this environment. Synthetic requests use the real reservation ledger with zero cost. Public-page fetching and provider outputs are replaced only by the dedicated acceptance worker launcher; the API, stage evidence validation, queue, PostgreSQL and frontend bridge remain real. This verifies integration, not real scraping/provider quality.

On this Windows machine, Docker-internal connectivity passes while direct localhost8094 forwarding fails with mirrored WSL networking. A reversible fallback is included; no machine-wide networking settings are changed:

```powershell
python backend/scripts/native_local_gateway.py
```

Open `http://127.0.0.1:8095`. The helper binds Windows loopback only and forwards HTTP through `docker exec` to the task-owned frontend listener. It does not expose Docker's socket, target arbitrary upstream URLs, log request bodies or put backend bearer credentials in the browser. It is a local preview utility, not a deployment server. Stop it with Ctrl+C. Standard localhost8094 mapping remains the normal route where Docker forwarding works.

For the real-browser acceptance, use a local virtual environment with `playwright==1.55.0`. A local Edge installation is used by default; otherwise install Playwright Chromium or set `FRONTEND_BROWSER` to a local Chromium executable. Export synthetic account credentials to an ignored local fixture file without displaying them:

```powershell
docker cp native-acceptance-native-bootstrap-1:/fixtures/accounts.json tmp/native-acceptance-accounts.json
python backend/scripts/validate_native_browser.py --fixtures tmp/native-acceptance-accounts.json --base-url http://127.0.0.1:8095
docker compose --env-file .env.native-integration-local -p native-acceptance -f compose.native-integration.yml --profile test run --rm --no-deps --build native-check python -m tests.native_support_check
```

The browser test submits the actual product wizard, starts fresh native preparation, reviews sources/people/qualification/outreach, records synthetic approval with `sent:false`, exercises pause/resume, checks four roles and tablet/mobile layout, and captures ignored screenshots under `tmp/native-actual-browser`. It does not substitute mock API responses.

Run the HTTP fixture journey, then browser acceptance, then the support-contract check, in that order on a fresh acceptance project. They intentionally leave synthetic decisions/history in that disposable database. Bootstrap is repeatable, but the mutating acceptance sequence is not a reset operation. To repeat the complete sequence, recreate **only this task-owned project**:

```powershell
docker compose --env-file .env.native-integration-local -p native-acceptance -f compose.native-integration.yml down --volumes
```

That removes this project's disposable data/accounts. Without `--volumes`, cleanup retains them. It does not operate on the existing `marketing-rebuild`, legacy app or DEV services. Stop the optional gateway separately. Re-export account fixtures after recreation; old fixture passwords/IDs are no longer valid.

## Additive APIs and compatibility

All workspace routes below require an expiring bearer session and existing membership. Native routes still have no `/api` prefix. Existing bare-list responses remain available; no envelope replacement is imposed on the frontend.

| Route | Role | Contract |
| --- | --- | --- |
| `GET /auth/me` | Signed-in user | `id`, `email`, `capabilities.create_workspace`, `expires_at`. Platform capability is independent of workspace ADMIN. Revoked/expired/inactive-user sessions return401. |
| `GET /workspaces/{wid}/leads/{lid}` | Any member | Identity, `created_at`, latest `current_preparation` or null, supported `primary_contact` or null. Works outside the first100 records. Wrong-workspace/missing IDs return404. |
| `GET /workspaces/{wid}/leads/page` | Any member | `{items,total,limit,next_cursor,as_of}`. Optional `q`, preparation `status`, `limit`1–100(default25), `cursor`. |
| `GET /workspaces/{wid}/catalog/all` | Any member | Active and inactive items, with `active` and context `version`; ordered by kind/code. |
| `PATCH /workspaces/{wid}/catalog/{cid}` | ADMIN | Strict `{active:boolean}`; returns `{id,code,active}`. No hard delete. |
| `POST /workspaces/{wid}/approvals/{aid}/revision` | ADMIN/OPERATOR | Human edit after CHANGES_REQUESTED; request/response below. |

Lead pagination orders by `created_at DESC, id DESC`; its opaque cursor binds workspace/search/status and the first page's `as_of`. New leads created after that boundary do not enter subsequent pages. `q` is literal case-insensitive company-name search; `%`/`_` are escaped. `status` matches the latest preparation only. `total` counts filtered records, not just the page. Filters cannot change while retaining the same cursor. Invalid/mismatched cursors return422.

Pagination is a live view bounded by lead creation time, not an immutable transaction snapshot: preparation statuses and company edits may change between reads. Restart from page one to refresh those filters. Existing leads receive their migration-time creation timestamp, with UUID tiebreak ordering. Existing `/leads` remains capped100 but now has deterministic ordering. Job/approval/history list caps remain100/100/50; their pagination is a later scaling slice.

Typed progressive results preserve absent stages rather than inserting null completed results. `RESEARCH.industry` is a sourced Finding object or null, not necessarily a string. `CONTACT_SEARCH.unavailable_queries` is an **integer count**. Jobs expose public history/result only; lease tokens, checkpoints and secrets remain private. Job result JSON covers several stage/standalone shapes; detailed stage schemas live under preparation results.

## Human revision flow

```json
{
  "idempotency_key": "unique-revision-action-key",
  "expected_version": 1,
  "subject": "A revised subject",
  "body": "Human-reviewed draft text preserving documented company context.",
  "evidence": [{"source_url": "https://example.com/", "evidence_quote": "An exact saved source quote."}],
  "note": "Updated the opening following the reviewer request"
}
```

The example is a request shape; its quote is not usable real evidence. Subject/body/evidence follow existing draft limits; edit note is5–1000 characters. The parent must be the latest current-context approval with CHANGES_REQUESTED and the expected version. The API preserves channel, recipient and product code; this endpoint cannot silently change the outreach destination. Quotes must match the saved official evidence. Unsupported promise wording remains rejected. Free-form edited prose still requires human judgment; citation validity is not proof of every sentence's semantic truth.

Successful response: `201 {approval_id,run_id,version,status:"PENDING_APPROVAL",sent:false}`. The new version is parent version+1, with a new run and immutable snapshot. Parent draft/decision remain unchanged. Revision metadata retains editor, time, edit note and original reviewer note. One child per parent plus current-run checks prevent divergent competing revisions.

Reuse the same key and exact payload/actor/parent after an uncertain response. It returns the original revision creation response even if that revision was later decided; reread approvals for current status. Reusing a key with changed content returns409. Wrong version, stale context, newer run or simultaneous preparation also returns409. Unsupported evidence returns422.

Editors are ADMIN/OPERATOR; decisions remain ADMIN/REVIEWER. A human editor cannot approve their own revision, including an ADMIN editor: another authorized reviewer must do so. Original worker-generated drafts retain existing reviewer permissions. Rejection/change requests remain allowed. Neither revision nor any decision sends a message. AI regeneration from reviewer notes is not implemented; human editing is the implemented revision path.

## Catalog and setup semantics

Real edits/deactivation use the same lock/invalidation policy. Outstanding managed work blocks changes while enabled. Pause first; pending interrupted work is then failed with CATALOG_CHANGED, with history retained. No-op upserts/lifecycle repeats do not invalidate work or increment context versions, making partial wizard retries safe.

Catalog versions increment on actual edits and lifecycle transitions and travel in new context snapshots. Deactivate/reactivate or edit/revert cannot accidentally make an old approval current again. Existing snapshots retain their catalog references. Removing the last active PRODUCT or ICP pauses automation and clears its discovery schedule; resume refuses until both are restored. Reactivation alone does not resume the product. Explicit resume restores an immediate discovery schedule if the ready product has no saved schedule. No hard-delete endpoint exists.

Product wizard catalog upserts and activation remain separate transactions. Partial save behavior is supported: retain fields, show which offerings saved and retry unchanged requests. Activation reuses its own idempotency key after uncertain responses; catalog no-op retries are safe even when the setup job is now pending. There is no atomic batch wizard endpoint in this slice.

Migrations006/007 add lead ordering timestamps/indexes, immutable revision metadata and catalog context versions. New snapshot fingerprints include catalog versions; pre-change approvals may become stale and require a fresh preparation run. Downgrade refuses to destroy revision/evidence history; use an explicit reconciled recovery migration.

## Frontend owner adaptations

1. Add `/auth/me` to the BFF's authenticated session/profile flow; never forward its backend bearer token to the browser. Use `capabilities.create_workspace` for platform controls.
2. Allowlist lead detail and `/leads/page`; forward only validated query parameters. The current bridge drops upstream query strings, so adding a route alone will not enable pagination. Switch list/detail adapters to the new contracts while retaining workspace-bound cache/request behavior.
3. Allowlist `/catalog/all` and PATCH catalog lifecycle for ADMIN. The current gateway accepts GET/POST/PUT only; add PATCH deliberately with CSRF and role checks.
4. Allowlist POST approval revision for ADMIN/OPERATOR. Add reviewer-note/edit/resubmit UI and refresh approval versions/stale state. Hide/disable approval when the current user is the human editor; backend403 remains authoritative. Use `snapshot.revision.editor_id` and `/auth/me.id`.
5. Fix People rendering to treat `unavailable_queries` as an integer count; the current frontend code calls `.map()` on nonzero values. Update “request changes requires fresh preparation” copy after the revision adapter is connected.
6. Retain same-origin opaque HttpOnly sessions and CSRF workspace switching. Process-local frontend sessions remain local-only; shared session storage/production ownership is still joint frontend/platform work.

New endpoints are verified at the backend; availability does not automatically expose them through the existing frontend bridge. Existing screens passed the real integration journey without modifying frontend files. The noted nonzero-search rendering issue and new controls remain frontend adaptations, not silently completed UI features.

## Verification and remaining scope

- 37 PostgreSQL integration tests passed: existing30 plus seven frontend-support tests, including116-record pagination, role/capability/revocation checks, actual worker scheduling, immutable/idempotent revisions, version/evidence/stale conflicts, separate reviewer, lifecycle and no-op setup retries.
- Actual HTTP API/BFF/PostgreSQL/worker acceptance passed for two unrelated products, industry evidence, contact review/continuation, provider failure/retry, pause/resume, four roles and tenant isolation.
- Headless Edge acceptance passed through the actual stack for product wizard, fresh preparation, research/people/score/draft review, synthetic approval without sending, pause/resume, role controls and tablet/mobile layouts.
- Separate HTTP checks using the actual restricted API role passed new paging/capability/revision/lifecycle operations, including immutable snapshot insert and different-reviewer enforcement.
- OpenAPI and normalized synthetic examples accompany this guide. Local gateway health returned200. No live provider spend, prospect outreach, SMTP, deployment or executor cutover occurred.

Source locations: [frontend_api.py](../backend/marketing_backend/frontend_api.py), [contracts.py](../backend/marketing_backend/contracts.py), [catalog_policy.py](../backend/marketing_backend/catalog_policy.py), [integration Compose](../compose.native-integration.yml), [OpenAPI](contracts/native-backend-openapi.json), [synthetic response examples](contracts/native-backend-examples.json), [support tests](../backend/tests/test_frontend_support.py) and [browser runner](../backend/scripts/validate_native_browser.py).

BE-07 team/accounts, BE-08 encrypted provider connections, BE-09 imports, BE-10 separate sending and BE-11 migration/cutover remain separate work. Real-provider calibration is not established by synthetic acceptance. Existing deployed app/n8n remains active. All PRs target `develop`; production is separate.
