# Native lead discovery and human acceptance

Implemented locally on 11 October 2026. This supersedes the earlier automatic candidate acceptance policy. The deployed legacy executor is not switched by these source changes; native DEV cutover and live provider calibration remain release work.

## Worker flow

Brave searches for observable customer business types and geography using the active workspace catalog and targeting. Python filters directories/social sites before budgeting, prioritizes homepages and excludes that workspace's known/reviewed domains. Queries remain bounded to 400 characters / 50 words. Up to three searches return up to 20 results each; a batch fetches at most ten pages, at most three per company. Batch size is a maximum rather than a guaranteed number of candidates.

The existing DNS-pinned, robots-aware public fetcher collects homepage and useful about/company/services/contact links. Trafilatura extracts readable company text. xKiro assesses each company separately against the real offerings and ICPs, returns a suggested industry, fit explanation, confidence and unknowns, and selects a numbered excerpt. The application saves the selected fetched source URL and exact text rather than model-written quotes. Unknown excerpt IDs, unsupported names, foreign ICP codes and unverified identity are rejected. Native recommendations below 50% confidence are excluded; this confidence is a model assessment, not a calibrated probability or proof of buying intent. The legacy adapter retains its existing 75% threshold.

One malformed company assessment or unavailable website does not discard successful companies. Search outages are distinguished from a legitimate no-match batch. Provider configuration, pricing and budget failures still stop the job. Per-company failures and final search/site/page/assessment/candidate counts are visible in the dashboard.

## Review gate

Discovery saves `READY_FOR_REVIEW` candidates in the workspace's existing `discovery_memory` table; it creates no lead, research job or preparation run. PostgreSQL permissions also prevent the native worker role from inserting leads.

An Administrator, Operator or Reviewer can explicitly Accept or Reject; a Viewer can read. Acceptance locks the workspace and candidate, checks current catalog/targeting and company-domain duplication, records the authenticated reviewer/time/note, creates one official lead and queues research in the same transaction. Repeated/concurrent acceptance returns the same lead and run. Catalog changes require reassessment. Paused automation blocks acceptance that would start preparation. Manual Add company uses the same workspace lock and domain duplicate check. A company added while discovery runs is rechecked before candidate persistence.

Rejection records a reason and retains the company in workspace memory. Accepted, known and rejected companies remain excluded. Pending candidates are excluded for their current context; context changes make unreviewed assessments eligible again. Failed fetches/assessments become eligible after one hour; no-match assessments after 24 hours. Reassess queues a targeted discovery job for that company's recorded website without requiring another Brave search. Reviewed companies cannot be retried through this action. Existing historical automatic acceptances are preserved without inventing human reviewer records.

After human acceptance the existing native preparation chain continues: Research → Contact search/review → Scoring → Product matching → Outreach draft → Pending human approval. Discovery acceptance does not approve outreach or send a message.

## Optional browser rendering

Ordinary guarded HTML fetching is the default. For JavaScript-heavy pages with little or no readable initial text, enable `BACKEND_DISCOVERY_BROWSER_FALLBACK=true` in the platform's ignored backend configuration and rebuild the worker through `compose.backend.yml`. This installs Chromium only in the worker image. Trafilatura and Playwright are pinned in `backend/requirements.lock`.

Browser requests are intercepted and fulfilled through the same DNS-pinned fetcher. Requests/redirects stay on the same hostname, robots rules apply, POSTs/private destinations and unrelated assets are blocked, service workers are disabled, WebSockets are closed and downloads are disabled. Rendering has a bounded wait, at most 20 asset requests and a two-megabyte request budget. Sites dependent on third-party scripts, authentication or blocking challenges may remain unavailable. Disabled/missing browser support produces an explicit per-company reason; it does not claim successful scraping.

Brave/xKiro credentials and provider rates use the existing platform worker configuration once. Product teams supply the catalog and targeting through the form. No separate n8n template or per-product provider keys are required by the native flow.

## API and frontend handoff

All routes require an authenticated workspace member and enforce workspace RLS.

| Route | Purpose |
| --- | --- |
| `POST /workspaces/{wid}/discovery` | Queue discovery; existing idempotency key contract |
| `GET /workspaces/{wid}/candidates` | Paged inbox/history; `status`, `limit` (1–100), `offset` |
| `GET /workspaces/{wid}/candidates/{cid}` | Evidence, recommendation, failure/review state and stale flag |
| `POST /workspaces/{wid}/candidates/{cid}/accept` | Body `{ "note": "" }`; return candidate/lead/run IDs |
| `POST /workspaces/{wid}/candidates/{cid}/reject` | Body `{ "note": "Reason of at least five characters" }` |
| `POST /workspaces/{wid}/candidates/{cid}/retry` | Queue targeted reassessment; return job ID |

`dashboard/app/native.py` allows these routes through the CSRF-protected BFF. `dashboard/app/static/native.js` provides a paged review inbox with suggested industry, ICP fit, source evidence, unknowns, Accept/Reject/Reassess actions and explicit confirmation text. `docs/contracts/native-backend-openapi.json` contains the refreshed schema.

Migration: `008_discovery_review`, independent of legacy migrations. It adds review/source-job/context/lead linkage and preserves existing memory. Downgrade is intentionally refused because it would discard review history.

## Legacy compatibility and release

The existing `/api/automation/candidates` endpoint now saves a review candidate and reports `READY_FOR_REVIEW`, with no automatic acceptance. Existing user acceptance already schedules research atomically for managed products. Workspace contracts now require human candidate review for both named and shared-job credentials. n8n sources and the checked-in preflight agree with this policy; the shared node is named Save Review Candidate, and dashboard summaries count candidates rather than accepted leads.

Deploying the legacy changes requires coordinated publication of the updated n8n preflight guards in all shared children and the API; old published guards expect the superseded contract. Pause the dispatcher, let active jobs settle, publish matching guarded children/API, then resume. Publishing source JSON alone does not update running n8n workflows. Native cutover requires provisioning the native runtime, catalog/accounts/provider configuration and one-executor ownership; do not point the replacement schema at the legacy database or enable both discovery executors for the same product. See [native worker migration plan](native-worker-migration-plan.md).

## Verification

50 real PostgreSQL backend tests pass, including manual acceptance, concurrent idempotency, rejection, targeted retry, stale context, workspace RLS, worker INSERT denial, partial assessment failure, concurrent manual company creation and actual Chromium rendering/private-network denial. Nine frontend BFF groups and the synthetic browser journey pass, including explicit acceptance. An actual local browser journey through the normal product form/BFF/restricted API/native workers confirms no lead before Accept and exactly one lead afterward. The actual two-product API/worker acceptance also passes. External search/model/fetch responses are synthetic; live extraction quality is not established by these checks.

Legacy shared automation regression passes against a separate disposable API/PostgreSQL project, including denial of acceptance through discovery leases and human-triggered research. All 79 n8n tests pass. Existing login/session (13) and UX (5) checks pass. CI now runs native PostgreSQL workers and an isolated Chromium regression in addition to the existing legacy/dashboard suites. No live provider calls, emails or runtime cutover were performed for this implementation.
