# Native marketing frontend

Implemented in the isolated `geekedctrl/redesign-frontend` branch against the 11 October 2026 native backend handoff and OpenAPI snapshot. The native backend implementation is in the separate `rebuild/python-backend` checkout at checkpoint `721a44f`. This frontend branch does not contain that backend. Older campaign roadmap and legacy API notes are historical context for this work.

## Backend support integration — 11 October 2026

The backend support branch `rebuild/native-frontend-support` now implements BE-01 through BE-06. Its [support guide](native-frontend-backend-support.md), refreshed OpenAPI and normalized response examples are copied into this frontend branch. The frontend has adapted to these contracts:

- `/auth/me` supplies public identity and explicit platform capability through the BFF session response. Tokens remain server-side; workspace ADMIN is not treated as platform admin.
- Leads use `/leads/page` with company search, current preparation status, stable cursors, filtered totals and previous/next controls. The bridge validates and forwards only supported query parameters. Filter/page context survives lead-detail navigation and is cleared on workspace switch or sign-out. Direct lead detail works independently of the old capped list.
- Product setup exposes active/inactive catalog items and ADMIN-only deactivation/reactivation. Active managed work prompts a pause before changes. Historical context is preserved; reactivation does not automatically resume automation.
- Requested changes can be edited and submitted as a new immutable approval version, with source-backed citations, optimistic version, request idempotency and retained reviewer notes. Channel, recipient and product are fixed. The human editor's Approve control is disabled; another authorized reviewer must approve.
- People renders `unavailable_queries` as an integer count, including nonzero counts.

The original actual-native browser journey and the new support-controls browser journey both passed against the disposable `native-acceptance` PostgreSQL/API/worker stack through localhost8095. These are actual API/queue/database integration tests with synthetic providers/evidence, not mocked API responses. The earlier connectivity blocker below is historical: Docker's Windows host forwarding still fails, but the supplied local loopback gateway provides a working integration path. Production sessions, provider calibration and release/cutover remain separate work.

## Run locally

Install `dashboard/requirements.txt` in a local virtual environment. From `dashboard/`:

```powershell
$env:NATIVE_API_BASE_URL = 'http://127.0.0.1:8020'
python -m uvicorn app.native:app --host 127.0.0.1 --port 8093
```

Open `http://127.0.0.1:8093`. Sign in with an account provisioned in the **native** backend; legacy accounts/IDs cannot be substituted. The frontend server calls native `/auth` and `/workspaces/{wid}` routes; the browser only calls its own origin. No CORS or browser bearer-token storage is needed. The existing `app.main:app` dashboard remains independently available.

The native frontend needs no provider keys, database credentials, or dashboard signing secret. Its browser cookie contains a random opaque session identifier, with HttpOnly and SameSite Strict. Bearer tokens and CSRF tokens are kept on the frontend server. Sessions expire after 12 hours; logout revokes the native session. Set `DASHBOARD_SECURE_COOKIES=true` when running behind HTTPS.

Session storage is currently process-local and intentionally suited to a **single local frontend process**. Restart signs users out. A shared expiring session store, hosting policy and authentication architecture review are release dependencies before multiple workers/production. Do not deploy this entry point as an automatic replacement for the existing dashboard.

If the host cannot reach port 8020, run the frontend server inside the backend's Docker network. The supplied acceptance stack uses `http://backend-api:8000` internally, browser port8094 normally, and the backend's loopback gateway on8095 where forwarding fails. See [integration commands](native-frontend-backend-support.md). Actual native browser integration has now passed through this gateway.

## Implemented journey

- Sign-in, expiry/error handling, sign-out, membership-checked workspace switch, role-aware navigation, responsive drawer/collapsible sidebar, accessible tabs, and system/light/dark themes.
- Overview prioritizes pending non-stale approvals and current preparation stops. It uses bounded returned records and describes their limits.
- Administrator product wizard: description/targeting/preferences, actual catalog offerings, review and activation. Catalog upserts are separate transactions; partial saves are shown on failure. Uncertain activation retries keep the same idempotency key; edits create a new key.
- Discovery starts a bounded batch and displays job states/history and accepted companies. Lead intake accepts company name/public website; lead search/status filters and cursor pagination run on the backend.
- Lead detail keeps company/contact above Overview, Research, People, Qualification, Outreach and Activity tabs. Partial stage results survive stopped work. Research presents source quotes, confidence, observed/inferred distinctions, unknowns and coverage. People allows saved supported contact/profile selection, source-backed manual continuation and contact-search retry.
- Qualification explains score components, criterion points/evidence and catalog matches. No unsupported qualification override exists.
- Approval displays the immutable saved draft, saved company/contact/qualification and research. Every decision requires a 5–1000 character note. Explicitly stale approvals disable Approve. Requested changes allow a sourced human revision and separate review; approval never sends.
- Operations shows pause/resume, failed-job retries, current/historical preparation, attempts/history, last observed provider outcomes and bounded reservations. Usage is not displayed as reconciled billing, lifetime spend or remaining budget.

The API bridge allowlists native routes and enforces role restrictions in addition to upstream authorization. Switching workspace rotates CSRF, aborts browser requests, clears visible records/forms/selections, and refuses old-workspace requests. Workspace mutations are serialized with switching. Untrusted evidence/draft text is escaped, external links restricted to public HTTP(S) shapes, and CSP restricts scripts and connections to this origin.

Active jobs poll at 10-second intervals. Updates preserve dirty forms, active tabs and scrolling; hidden pages suspend normal polling. Requests are not automatically resubmitted after asynchronous failures. Errors remain in forms with entered values intact.

## Verification

```powershell
python dashboard/scripts/validate_native_frontend.py
python dashboard/scripts/validate_native_frontend.py --browser
node --check dashboard/app/static/native.js
```

The browser option requires Playwright (`python -m pip install playwright`) and local Edge, or `FRONTEND_BROWSER` pointing to a Chromium executable. On Linux install Playwright Chromium. Tests run a temporary frontend server backed by in-process synthetic native API responses; they never connect to providers, live workspaces or SMTP. Screenshots are written under ignored `tmp/native-ui-review/`.

Eight BFF test groups cover token isolation, CSRF, expiry/logout, four-role permissions, route allowlisting, stale rejection, source links, workspace isolation, public profiles, query forwarding/validation and catalog permissions. Synthetic browser acceptance additionally exercises pagination/search/older lead detail, nonzero unavailable-search counts, catalog lifecycle and immutable revision/separate-review controls alongside the original journey.

Actual support browser acceptance, using private synthetic fixtures exported from the supplied acceptance stack:

```powershell
python dashboard/scripts/validate_native_support_browser.py --fixtures tmp/native-acceptance-accounts.json --base-url http://127.0.0.1:8095
```

This runner refuses non-loopback URLs and non-synthetic fixture accounts. It mutates only the disposable acceptance environment: fresh native preparation, requested changes, revision, separate review, and catalog deactivate/reactivate/resume. It verifies query cursors, identity/capabilities, immutable parent snapshots and persistent stale context. Screenshots go to ignored `tmp/native-support-browser`. Run it after the backend's original actual browser journey; these tests leave synthetic history and are not reset operations. Keep fixture credentials ignored and do not display them.

## Backend dependencies

Remaining native APIs include invitations/team provisioning, account recovery/settings, imports, provider connection management and native sending. Atomic setup remains intentionally unsupported: separate catalog upserts and activation have verified partial-save/idempotent retry semantics. Jobs/approval/history lists remain capped100/100/50. No fake working controls are exposed for unavailable features.

Before release: agree production session storage, complete remaining API parity and reviewed data/account/approval migration/executor cutover, and obtain release authorization. Local native integration is verified with synthetic providers; it does not establish real-provider quality. PRs target `develop`; deployment and merge remain separate user decisions.
