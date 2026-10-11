# Backend handoff: support for the native frontend

Prepared 11 October 2026 by the frontend owner. This is a task brief for the backend agent; it does not authorize deployment, provider spend, real outreach or executor cutover.

## Follow-up status — 11 October 2026

BE-01 through BE-06 are implemented in `rebuild/native-frontend-support`; see [backend support report](native-frontend-backend-support.md). The frontend adapters and actual native browser validation now pass, including profiles, query forwarding/paging/detail, integer contact-search counts, catalog lifecycle and immutable revisions with separate review. The brief below is retained as the original requirements, not a request to redo completed work. BE-07 through BE-11 and joint production session architecture remain later slices.

## Starting point

Frontend branch: `geekedctrl/redesign-frontend`, with local uncommitted implementation. Backend reference: separate `rebuild/python-backend` checkout, checkpoint `721a44f`. Verify current Git status and read the latest backend docs before starting; these references are a baseline, not a claim that either branch is published or unchanged.

The frontend consumes the native backend directly through a same-origin server bridge. It does not use legacy `/api` routes or n8n. The implemented screens cover login, workspace switching, overview, product setup, discovery, leads, preparation/contact review, qualification, draft approval and operations. See [frontend implementation](native-frontend.md) and [original backend-to-frontend brief](frontend-native-backend-handoff.md).

Six server-bridge test groups and headless Edge acceptance pass against synthetic responses. Actual native database/worker/browser integration has **not** passed yet. The deployed legacy app remains separate.

## Ownership and working boundaries

Implement backend changes in an isolated backend branch/worktree. Preserve existing user changes. The backend agent owns native API/models/workers/migrations and backend tests; the frontend owner owns `dashboard/app/native.py`, native templates/static files and frontend browser tests. Report new contracts and required frontend adaptations instead of silently modifying the frontend bridge or enabling controls.

Read `docs/ai/HANDOFF.md`, `PROJECT_STATE.md`, `TASK_BOARD.md` and the latest native-worker notes in the backend checkout. The older campaign roadmap is historical for this task. Use synthetic accounts, companies and providers. PRs target `develop`; do not merge, deploy, disable deployed n8n, contact prospects or call paid providers.

## Priority 0: unblock actual local integration

### BE-01 — Reliable frontend-to-native API connectivity

Observed on 11 October:

- Containers `marketing-rebuild-backend-api-1`, `marketing-rebuild-backend-worker-1` and `marketing-rebuild-backend-db-1` are running.
- Native API publishes `127.0.0.1:8020 -> 8000/tcp`.
- Container-internal `/health` returns `{"status":"ok","backend":"python-workers"}`.
- Windows host `http://127.0.0.1:8020/health` fails with connection refused.

Investigate binding, service health and Docker Desktop forwarding without altering deployed environments or removing existing containers/volumes. Alternatively provide a reproducible **local integration** Compose configuration connecting the independent native frontend service to the native API through an internal Docker network. Use the actual API service hostname; document it rather than guessing.

Acceptance: from the frontend server runtime, health, login and workspace-scoped reads succeed; from the browser, the frontend is reachable. Document exact startup commands, network names/service URLs, ports and cleanup limited to task-owned resources. No production/network cutover is required.

### BE-02 — Disposable native-worker acceptance environment

Provide a repeatable fixture/bootstrap command for two unrelated products and ADMIN/OPERATOR/REVIEWER/VIEWER accounts, backed by a disposable native database and synthetic providers. Do not commit credentials or provision fixtures into existing workspaces. Support deterministic cases for contact review, stale approval, provider failure, retry, paused automation and historical failure followed by current success.

Acceptance: execute the frontend journey through the **actual native API, database and workers**, ending in a pending approval, followed by an explicitly reviewed synthetic decision returning `sent:false`. Preserve evidence snapshots and demonstrate tenant isolation. Capture executed commands/results and limitations. Existing `validate_native_frontend.py --browser` uses a mocked upstream; its success does not satisfy this acceptance item. Coordinate a real-backend browser runner with the frontend owner.

## Priority 1: contracts required for robust current screens

The routes and shapes below are **proposals**, not already available APIs. Agree additions with the frontend owner and prefer additive compatibility.

### BE-03 — Typed response contracts and current-user capabilities

Add typed response models for workspaces, leads, catalog, jobs, preparation/history, approvals and operations, including progressively absent stage results. Export a refreshed OpenAPI snapshot and deterministic response examples. Preserve the separate preparation/job/approval state machines and explicit approval `stale` flag.

Proposed `GET /auth/me` response: user ID, email/display name if supported, and explicit `capabilities.create_workspace`. Capability must reflect platform-administrator authorization; workspace ADMIN must not imply platform admin. Define expiry/revocation semantics. Never expose password hashes, bearer-token hashes, provider secrets or worker lease tokens.

Acceptance: schema/source/test examples agree; all four roles and platform-versus-workspace administration are verified. Record compatibility notes in the frontend handoff. The frontend currently derives workspace role from `GET /workspaces` and has no profile endpoint.

### BE-04 — Single-lead detail and ordered server-side lists

Proposed `GET /workspaces/{wid}/leads/{lid}`: stable company identity, website and supported current contact, with current preparation ID/status/stop reason or documented links to retrieve them. Apply the same workspace authorization as other records.

The frontend currently resolves identity from the capped 100-record lead list. This prevents reliable links to older leads. Add deterministic ordering, pagination and documented search/status filters to lead lists. Define totals, cursor/page semantics and maximum limits; distinguish filtered totals from sampled records. Define pagination for approval/job/history lists as the next scaling step.

Acceptance: lead detail works outside the first list page; cross-workspace IDs return a consistent unavailable response; repeated pagination has no duplicate/omitted records under documented ordering; lead status comes from the latest/current preparation, never an older failure.

Changing bare-list responses to envelopes is breaking for the current frontend. Introduce an additive/versioned contract or coordinate the adapter change before removing the old shape.

### BE-05 — Review changes, draft revision and resubmission

Currently `CHANGES_REQUESTED` records a note but there is no editing/resubmission handler; a fresh preparation run is needed. Define a source-backed revision flow that surfaces the reviewer note, permits authorized editing and creates a **new immutable approval snapshot**. Decide explicitly whether revision reruns drafting, accepts human edits, or supports both; do not imply the review note is consumed until implemented.

Require optimistic versions/current-context checks and idempotency for uncertain retries. Retain the previous draft and decisions for audit. Document editor/reviewer permissions and whether self-review is permitted. No revision or approval may send a message.

Acceptance: stale/conflicting edits fail safely; a revision cannot mutate an existing approval snapshot; request changes can be followed by a reviewable new revision; old approvals cannot approve newer content; all decisions retain actor, time and note.

### BE-06 — Catalog lifecycle and product setup semantics

Current catalog upserts and activation are separate transactions. The frontend retains fields and reports partial saves. Add offering deactivation with documented effects on active preparation and stale approvals; preserve historical catalog references/snapshots. Do not hard-delete referenced offerings.

Confirm idempotency when setup succeeds but its response is lost. If atomic setup is required, propose a validated batch setup endpoint with transaction semantics; otherwise document partial-save behavior as supported. Existing/generated ICPs must remain product-specific and readable. Document preferences returned by operations after activation and pause/resume/retry behavior.

Acceptance: partial saves and retries are predictable, context changes invalidate old approval correctly, unrelated product catalogs stay isolated, and an existing offering can be deactivated without corrupting history.

## Priority 2: broader product APIs, separate slices

| Task | Backend requirements | Frontend implication |
| --- | --- | --- |
| BE-07 Team and accounts | Membership listing, invitations/provisioning, role changes/removal, account settings and recovery; specify platform/workspace administration and session revocation. | Native Team/account flows can replace unavailable legacy controls. |
| BE-08 Shared provider connections | Encrypted connection management/rotation with explicit admin capabilities, redacted status and audit events; ordinary workers never supply keys. | Connection screens can explain configuration failures without exposing secrets. |
| BE-09 Imports | Native company/contact import preview, validation, duplicates, bounded commit and per-row results; define public-source provenance requirements. | CSV/business-card intake can be adapted to native records rather than legacy IDs. |
| BE-10 Sending parity | A separately scoped sending API with immutable recipient/content approval, workspace SMTP configuration, suppression, idempotency and uncertain-handoff safeguards. | A Send control is only added after separate sending acceptance/authorization. Approval remains `sent:false`. |
| BE-11 Migration/cutover | Explicit account/record/approval mapping, tested migration/rollback and one-executor ownership. | Native and legacy IDs remain distinct; existing app/n8n stays active until reviewed cutover. |

These are backlog slices, not prerequisites for the synthetic frontend preview. Do not silently broaden BE-01/02 into provider setup, paid calibration or deployment. A separate candidate accept/reject queue is also optional: native discovery currently accepts supported companies automatically.

## Authentication and frontend coordination

The frontend already implements the agreed same-origin BFF approach:

- Browser calls `/session/*` and `/gateway/{wid}/...` on its own origin.
- Bearer credentials remain on the frontend server; browser cookie is opaque, HttpOnly and SameSite Strict.
- CSRF rotates on workspace switch; requests for a previous workspace are rejected.
- Upstream mutations retain backend authorization; frontend bridge checks roles too.
- Native upstream routes have no `/api` prefix.

Do not add broad CORS or require browser bearer storage to fix integration. If native cookie sessions are proposed, coordinate that architecture change explicitly. Current BFF sessions are process-local for one local frontend process. A shared expiring store/release architecture is **joint frontend/platform work**, not an existing native API defect. Agree production session ownership, rotation/revocation and deployment policy before multiple frontend workers or production.

Any new route needs a frontend bridge allowlist/role update and screen adapter; backend availability alone does not expose it. Notify the frontend owner of request/response/status/permission changes, including renamed fields and newly required validation.

## Source map

| Purpose | File |
| --- | --- |
| Frontend server sessions/native bridge | `dashboard/app/native.py` |
| Screens, state handling and request payloads | `dashboard/app/static/native.js` |
| Native shell and styling | `dashboard/app/templates/native.html`, `dashboard/app/static/native.css` |
| Synthetic fixture shapes and acceptance | `dashboard/scripts/validate_native_frontend.py` |
| Current portable contract | `docs/contracts/native-backend-openapi.json` |
| Native auth/catalog/leads/jobs | `backend/marketing_backend/api.py` in backend checkout |
| Preparation/contact/approval/operations | `backend/marketing_backend/native_api.py` in backend checkout |
| Evidence/stage results | `backend/marketing_backend/stages.py` in backend checkout |
| Queue, snapshots and transitions | `backend/marketing_backend/pipeline.py` in backend checkout |
| Backend fixtures/integration | `backend/tests/test_native_pipeline.py`, `test_backend.py`, `runtime_smoke.py` in backend checkout |

## Completion report expected from backend agent

Return implemented task IDs, branch/checkpoint, changed APIs and migrations, regenerated OpenAPI and example responses, exact synthetic tests executed/results, reproducible integration commands, remaining dependencies and frontend adaptations required. Separate executed real-native tests from mocked frontend checks. Update the backend-to-frontend handoff and engineering state docs so the frontend owner can continue from verified contracts.

Recommended order: **BE-01 connectivity → BE-02 actual integration → BE-03 typed contracts/capabilities → BE-04 detail/lists → BE-05 revisions → BE-06 catalog lifecycle**, then separately scoped broader APIs. Confirm existing behavior before duplicating functionality added after checkpoint721a44f.


### Discovery review update — 11 October 2026

Discovery now waits for explicit user acceptance before lead creation/research. See [native lead discovery](native-lead-discovery.md) for candidate APIs, native UI/BFF adapters, migration008, worker libraries/limits, local acceptance and coordinated release requirements. Earlier automatic discovery acceptance guidance is superseded.
