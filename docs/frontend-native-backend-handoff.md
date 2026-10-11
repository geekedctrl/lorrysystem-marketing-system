# Frontend handoff: native marketing system

Prepared 11 October 2026. This brief is for the developer rebuilding the frontend alongside the native Python backend.

## Objective and current state

Build a professional multi-product marketing application that ordinary workers can use without opening n8n, editing workflows or entering provider API keys. An administrator describes a product and enters its actual catalog through forms. Shared backend workers handle targeting, discovery, research, contacts, qualification, product matching and draft preparation. Human approval is the stopping point; sending is a separate future action.

Each product has its own workspace, team access, catalog, targeting, discovery memory and preparation records. A person must only see workspaces they belong to. The frontend must work for unrelated products, not assume every customer sells fleet software.

The replacement backend is implemented locally in `backend/`, on branch `rebuild/python-backend`, implementation commit `721a44f`. This handoff accompanies the native-worker PR targeting `develop`. Supply that PR checkout and these contract files to the frontend developer. The replacement runtime has not been deployed or connected to the existing dashboard; merging these files alone does not perform that cutover.

The deployed system still uses the original `api/`, `dashboard/` and n8n. Its existing UI is a design reference, not evidence that a feature exists in the replacement backend. Do not redirect the deployed dashboard or disable n8n during frontend development.

## Technology and source of truth

- Replacement backend: FastAPI JSON API, Pydantic, SQLAlchemy, PostgreSQL and native Python workers. No frontend-to-n8n calls are needed.
- Existing frontend: FastAPI/Jinja2 templates, custom CSS and vanilla JavaScript. React/Next.js has not been selected for the rebuild; a new frontend can consume the same API. Agree the frontend framework and browser authentication approach before integration.
- API contracts: [OpenAPI snapshot](contracts/native-backend-openapi.json), [core routes](../backend/marketing_backend/api.py), [preparation routes](../backend/marketing_backend/native_api.py) and [stage result definitions](../backend/marketing_backend/stages.py).
- The OpenAPI snapshot was exported from the running native API on 11 October. It describes requests and routes; many response schemas are currently untyped dictionaries. Use the response map below and source functions for response types. Regenerate the snapshot after backend changes.
- Latest native behavior overrides historical n8n routes, role assumptions and qualification thresholds in older documentation.

## Screens to implement

| Screen | Required behavior | Available native data/actions |
| --- | --- | --- |
| Sign in | Email/password, readable errors, session expiry and sign out. | `/auth/login`, `/auth/logout` |
| Workspace shell | Workspace switcher, role-aware navigation, account menu, responsive sidebar/drawer, light/dark/system themes. Clear workspace data and pending requests on switching. | `GET /workspaces` returns permitted workspace IDs, names and roles. |
| Overview | Pending approvals and unresolved current preparation first; automation status and recent activity. Show a clear next action. Avoid invented conversion/revenue metrics. | `/operations`, `/approvals`, `/jobs`, `/leads` |
| Product setup | Administrator wizard: product details → catalog → review/activate. Real offerings, description, optional target customers, country, language, voice and batch size. Existing/generated ICPs visible; advanced targeting optional. Pause/resume controls. | Catalog upserts followed by `/automation/activate`; status/preferences in `/operations`. |
| Discovery | “Find leads” starts a bounded batch and shows queued/running/completed/failed state, sourced results and accepted leads. Batch size is a maximum, not promised results. | `/discovery`, `/jobs/{jid}`, `/leads`; no standalone candidate-review API yet. |
| Leads | Company list with current preparation status and next action. Manual company/website entry and “Prepare lead”. Optional local search/filter of the returned sample, honestly labeled. | Lead list/create, `/prepare`, `/operations`. No backend pagination/filtering yet. |
| Lead detail | Company and primary contact cards **above** the research pane. Tabs: Overview, Research, People, Qualification, Outreach, Activity. Link back to the user's list context. | Lead list identity plus preparation results and linked jobs. No single-lead GET route yet. |
| Research | Readable company brief, grouped services/industry/fleet/technology/location, unknowns and coverage. Source links, expandable exact quotes, confidence and observed/inferred distinctions. No raw JSON as the main UI. | `results.RESEARCH` |
| People | Named people, roles, sourced public business contacts and professional links. Clearly distinguish ambiguous candidates and missing reachable contacts. Choose a supported person/profile, enter a source-backed contact, or retry profile search. | `results.CONTACT_SEARCH`, `/contact`, `/retry-contact-search` |
| Qualification | Explain criterion points, relevance versus opportunity, evidence, unknowns, adjustments and stop reason. Product matches show actual catalog names, fit, rationale and selected offering. | `results.SCORING`, `results.MATCHING`, catalog |
| Outreach | Professional subject/body preview, channel, recipient, selected product and supporting evidence. Status indicates pending approval/decision. No working Send button in this milestone. | `results.DRAFTING`, approval snapshot |
| Approvals | Queue and detailed immutable draft with company/contact/qualification context. Approve, reject or request changes with a required review note. Clearly label stale drafts and disable approval. | `/approvals`, `/approvals/{aid}/decision` |
| Activity / operations | Current failures, stalled/delayed jobs, attempts/retries, historical stage events, provider last observed outcomes and recent reservation/usage data. Technical details can be expanded. | `/operations`, `/jobs`, preparation history |

Team management, provider connections, SMTP setup, imports and account recovery are part of the broader product, but their replacement APIs are unfinished. Treat those as backend dependencies rather than presenting working controls backed by local mocks.

## User journey and permissions

Normal flow:

`Product form → catalog → activation → discovery → research → contact search → qualification → product matching → outreach draft → human approval`

Workers intervene only when evidence/contact/policy/configuration stops require a decision. Contact review is an exception when automatic selection cannot safely continue. Approval never sends a message, even when the response status is `APPROVED`.

| Workspace role | Read records | Find/add/prepare leads; contact resolution; retry jobs | Configure catalog; activate/pause/resume | Decide approvals |
| --- | --- | --- | --- | --- |
| ADMIN | Yes | Yes | Yes | Yes |
| OPERATOR | Yes | Yes | No | No |
| REVIEWER | Yes | No | No | Yes |
| VIEWER | Yes | No | No | No |

Creating a workspace currently requires a **platform administrator**, a capability separate from workspace ADMIN. The API does not yet expose that capability in a profile endpoint. Do not infer permission to create workspaces from the workspace role. API authorization remains authoritative even when UI controls are hidden.

## Integration contract

Native local API mapping is `http://127.0.0.1:8020`; docs are `/docs`, schema `/openapi.json`, health `/health`. Internal Docker access is verified. Windows host forwarding was previously unavailable despite the port mapping; resolve Docker Desktop networking before relying on browser access. See [backend setup](../backend/README.md) and [compose.backend.yml](../compose.backend.yml).

Login returns `{ "token": "…", "token_type": "bearer" }`. Authenticated requests send `Authorization: Bearer <token>`. Sessions expire after 12 hours; logout revokes the session. No native cookie session, CORS configuration, `/me`, invitations or password reset endpoint exists yet. Agree a same-origin proxy/server-side session approach with the backend developer; never embed provider keys or database credentials in the browser bundle or frontend repository.

The following workspace routes share prefix `/workspaces/{wid}`. Path IDs are UUIDs. Native routes have **no `/api` prefix**.

| Method and suffix | Request | Response / use |
| --- | --- | --- |
| `GET /catalog` | — | Active items: `id, kind, code, name, description, rules`. |
| `PUT /catalog` | One item: `kind: PRODUCT or ICP`, uppercase/digit/underscore `code`, `name`, `description`, optional `rules`. | `201 {id, code}`; upsert, not bulk replacement. |
| `POST /automation/activate` | Activation JSON below. | `202 {job_id, status}`; poll setup job. |
| `POST /automation/pause`, `/automation/resume` | No body. | `{enabled}`. Resume does not automatically retry failed interrupted jobs. |
| `POST /discovery` | `{idempotency_key}` | `202 {job_id, status}`. |
| `GET /leads` | No pagination parameters. | Up to 100 `{id, company_name, website}` records. Not guaranteed newest-first. |
| `POST /leads` | `{company_name, website}` | `201 {id, company_name, website}`; public HTTP(S) company website. |
| `POST /leads/{lid}/prepare` | `{idempotency_key, icp_code?}` | `202 {run_id}`; requires enabled automation and PRODUCT/ICP catalog. |
| `GET /leads/{lid}/preparation` | — | Up to 50 runs, newest first, with explicit `current` flag. |
| `GET /preparation/{rid}` | — | `id, lead_id, status, stop_reason, results, created_at`. |
| `POST /preparation/{rid}/contact` | Contact-choice JSON below. | `202 {run_id, status}`; resumes from saved research. |
| `POST /preparation/{rid}/retry-contact-search` | No body. | `202 {run_id, status}`; refreshes profile searches without repeating research. |
| `GET /approvals` | — | Latest 100: `id, run_id, snapshot, status, decision, created_at, stale`. |
| `POST /approvals/{aid}/decision` | `{decision, note}` | `{status, sent:false}`. Decision: APPROVED / REJECTED / CHANGES_REQUESTED; note 5–1000 characters for all decisions. |
| `GET /jobs`, `/jobs/{jid}` | — | Job state/result/history; list is latest 100. |
| `POST /jobs/{jid}/retry` | No body. | `202` job response; failed jobs only, context must remain current. |
| `GET /operations` | — | Automation settings, current preparations, stalled/delayed jobs and observed provider usage. |

`POST /leads/{lid}/research` is also available for standalone homepage-only review. Use `/prepare` for the primary full preparation journey.

Example activation after saving actual catalog offerings:

```json
{
  "idempotency_key": "setup-unique-action-uuid",
  "product_description": "A description of the real product and its documented capabilities.",
  "target_customers": "The types of businesses this product serves",
  "country": "MY",
  "language": "English",
  "brand_voice": "Professional and concise",
  "batch_size": 3
}
```

Product description is 20–5000 characters; target customers up to 2000; country is two uppercase letters; batch size is an integer 1–10. Catalog name is 2–120, description 10–5000, code up to 80. Strict requests reject extra fields. Catalog upserts and activation are separate transactions: retain form state and show partial-save/retry outcomes honestly; the current backend cannot promise an atomic wizard submission.

For a contact review stop, submit **one** of:

```json
{"person_index": 0, "profile_url": "https://www.linkedin.com/in/supported-person"}
```

```json
{
  "business_contact": {
    "name": "Supported Person",
    "role": "Operations Director",
    "email": "person@example.com",
    "source_url": "https://example.com/team",
    "evidence_quote": "An exact saved official-page quote containing this person's name, role and email."
  }
}
```

These are illustrative shapes, not usable fixture identities. Manual continuation currently requires a supported email; phone is optional. The quote must come from an official company page already saved in research and support the name, role and email. A selected profile must be an existing supported individual LinkedIn candidate. Do not promise that arbitrary private contacts or newly pasted URLs will resolve the stop.

## Result presentation and state handling

Preparation `results` is keyed by stage: `RESEARCH`, `CONTACT_SEARCH`, `SCORING`, `MATCHING`, `DRAFTING`. Keys arrive progressively and may be absent. Preserve partial results when work stops. Exact stage models and enriched return values are in [stages.py](../backend/marketing_backend/stages.py); deterministic examples are in [native pipeline tests](../backend/tests/test_native_pipeline.py).

| Result | Important fields / interpretation |
| --- | --- |
| Research | `facts[]`: category, statement, source_url, evidence_quote, confidence 0–100, kind OBSERVED/INFERRED; `people[]`; `unknowns[]`; saved `pages[]`; optional `industry`, `coverage`. Industry is sourced when supported, otherwise show “Not established from available sources”. Fleet is product-specific and optional. Do not derive a fake fleet number from prose. |
| Contacts | `people[]` with profiles and profile_candidates; `selected_contact`; unavailable_queries; stop_reason. Matching public name/company evidence is not proof of current employment. A business email without a supported name must not become an invented person. |
| Scoring | `criteria[]` with points, rationale and evidence; total `score`, `relevance`, `opportunity`, adjustments, unknowns and stop_reason. Relevance/opportunity are components of the total, not separately normalized 0–100 scores. Default rubric: ICP40, need30, scale15, signals10, evidence5. Automatic qualification needs total60 plus positive ICP fit. Do not represent score as purchase probability. |
| Matching | `matches[]` with product_code, fit, rationale and evidence; `selected_product`; stop_reason. Resolve catalog codes to real names. Default eligible fit is at least60. |
| Draft | subject, body, evidence, channel EMAIL/LINKEDIN, recipient, product_code, status. Render body as text with preserved paragraphs. Draft approval snapshot is authoritative for review, even if current lead data has changed. |

Preparation states include PREPARING, NEEDS_REVIEW, PENDING_APPROVAL, APPROVED, REJECTED, CHANGES_REQUESTED, FAILED and STALE. Job states are PENDING, RUNNING, COMPLETED, NEEDS_REVIEW and FAILED. Approval states are PENDING, APPROVED, REJECTED and CHANGES_REQUESTED. These are different state machines; a completed stage job is not a completed/approved preparation run. Use the approval's explicit `stale` flag, not only a preparation status, when disabling approval.

Use the **latest/current** run for lead badges and overview warnings. Keep older failures in Activity; a historical failed run must not make a newer successful run look broken. `GET /operations.current_preparation` provides the latest run for each lead; per-lead history also identifies `current`.

Show a specific reason and available next action for missing supported contacts, unavailable searches, insufficient company evidence, low qualification, no supported product match, paused automation, changed context and provider configuration/budget failures. Contact review has continuation APIs; low qualification/matching currently has no manual override. Configuration failures should direct a worker to an administrator rather than asking them for API keys.

Operations fields: `enabled`, `preferences`, `next_discovery_at`, `stalled_jobs`, `delayed_pending_jobs`, `current_preparation`, `provider_health`, `recent_provider_usage`, `cost_basis`. Provider health means **last observed request**, not an active health probe. Cost values `estimated_microusd / 1_000_000` are conservative USD reservations; actual reported token usage is separate. Recent usage is limited to 100 records. Do not label a sum as lifetime spend, an invoice or the global remaining budget.

Jobs expose `id, workspace_id, lead_id, kind, run_id, managed, status, attempts, max_attempts, result, failure_code, history, created_at, available_at, lease_until`. Workspace SETUP/DISCOVERY jobs have no lead/run ID. Lease tokens and provider secrets are never frontend data.

Generate a fresh idempotency key per activation, discovery or preparation action, keep it with that exact request and reuse it after uncertain network failures. A new intentional run uses a new key. Disable duplicate clicks. Poll visible active work at a modest interval (for example 10 seconds); stop timers/ignore late responses after switching workspace or navigating away. No SSE/WebSocket contract exists. Refresh must preserve dirty forms, open dialogs, selected tabs and scroll.

Handle 401 by returning to login, 403 with a permission explanation, 404 as unavailable/not found, 409 with conflict/stale-context recovery, 422 with field errors, and login429 with a retry-later message. Job provider failures are often saved asynchronously with failure_code; a successful202 only means queued. Do not turn every asynchronous failure into automatic repeated API submissions.

## Design and acceptance requirements

- Consistent typography, spacing, semantic colors, restrained badges and clear primary actions. No giant unformatted bullet dumps or raw provider output as the main research view.
- Desktop/tablet/mobile layouts; long company names, source URLs and draft bodies must wrap without page overflow. Tables may scroll within their container.
- Keyboard-accessible menus, dialogs and tabs; labeled fields, visible focus, status text beyond color, sensible headings and reduced-motion support. Preserve theme behavior.
- Every page needs loading, empty, partial, failed, permission-denied and successful states. Preserve valid form values when submission fails.
- Escape untrusted research/provider text. Validate external links to public HTTP(S) before rendering; use safe external-link attributes. Never render evidence or drafts as unsanitized HTML.
- Switching workspaces must clear previous workspace records, selections, query caches and outstanding requests. Cache keys include workspace ID. Role-hidden controls do not replace backend permission checks.
- Demonstrate two unrelated product workspaces, a complete synthetic pipeline to pending approval, contact review/continuation, stale approval refusal, pause/resume/retry, and historical failure followed by current success.
- Verify ADMIN/OPERATOR/REVIEWER/VIEWER behavior, keyboard navigation and responsive screens. Use synthetic data and mocked providers by default; no real email or paid provider tests as part of routine frontend verification.

Existing backend verification: 30 PostgreSQL integration tests and running restricted-role API/worker smoke passed. Those are backend/synthetic checks, not browser acceptance or evidence of real-provider quality.

## Backend dependencies to raise rather than fake

1. Browser session/CORS or same-origin proxy integration; current-user and platform capability discovery.
2. Single-lead detail, server-side pagination/search/filtering and reliable list ordering for larger datasets.
3. Web team provisioning/invitations, account settings/recovery, catalog deletion/deactivation and atomic product setup if required by the UI.
4. Draft editing/revision and resubmission. Request changes currently requires a fresh preparation run; notes are not consumed by an editing handler.
5. Encrypted shared provider connection management and rotation; richer evidence upload/contact override controls if desired.
6. Candidate review controls if a separate accept/reject discovery queue is required. Native discovery currently accepts supported companies automatically.
7. Separate native sending and per-workspace SMTP configuration, suppression and uncertain-handoff safeguards. Legacy sending exists, but the replacement has no sending endpoint.
8. Data/accounts/approval migration and tested executor cutover. Existing and native record IDs are not interchangeable.

## File map: where to look

| Information | Location |
| --- | --- |
| Current project priority and executed verification | [HANDOFF](ai/HANDOFF.md), [PROJECT_STATE](ai/PROJECT_STATE.md), [TASK_BOARD](ai/TASK_BOARD.md), [TEST_STATUS](ai/TEST_STATUS.md); read latest 11 October native entries. |
| Native setup, accounts and Docker commands | [backend/README.md](../backend/README.md), [compose.backend.yml](../compose.backend.yml), [backend/.env.example](../backend/.env.example) |
| API requests and routes | [OpenAPI contract](contracts/native-backend-openapi.json), [api.py](../backend/marketing_backend/api.py), [native_api.py](../backend/marketing_backend/native_api.py) |
| Result shapes and stage policies | [stages.py](../backend/marketing_backend/stages.py), [native worker guide](native-preparation-workers.md) |
| Roles, ownership and state transitions | [auth.py](../backend/marketing_backend/auth.py), [models.py](../backend/marketing_backend/models.py), [pipeline.py](../backend/marketing_backend/pipeline.py) |
| Synthetic examples for mocks | [test_native_pipeline.py](../backend/tests/test_native_pipeline.py), [test_backend.py](../backend/tests/test_backend.py), [runtime_smoke.py](../backend/tests/runtime_smoke.py) |
| Existing UX and layout | [dashboard-ux.md](dashboard-ux.md), [base.html](../dashboard/app/templates/base.html), [design-system.css](../dashboard/app/static/design-system.css), [app.css](../dashboard/app/static/app.css), [ui.js](../dashboard/app/static/ui.js), [theme.js](../dashboard/app/static/theme.js) |
| Existing product/lead/approval views | [product_setup.html](../dashboard/app/templates/product_setup.html), [lead_detail.html](../dashboard/app/templates/lead_detail.html), [approval_detail.html](../dashboard/app/templates/approval_detail.html), [automation_operations.html](../dashboard/app/templates/automation_operations.html) |
| Existing professional research and people presentation | [research-brief.md](research-brief.md), [research_presenter.py](../dashboard/app/research_presenter.py), [research_brief.html](../dashboard/app/templates/research_brief.html), [people_profiles.html](../dashboard/app/templates/people_profiles.html) |
| Broader business context / future sending | [product-onboarding.md](product-onboarding.md), [lead-preparation-pipeline.md](lead-preparation-pipeline.md), [preparation-reliability-and-sending.md](preparation-reliability-and-sending.md); historical legacy APIs require adaptation. |
| Native migration and cutover boundaries | [backend-rebuild.md](backend-rebuild.md), [native-worker-migration-plan.md](native-worker-migration-plan.md) |

Local `knowledge/README.md` indexes additional product, architecture and progress notes, but `knowledge/` is ignored by Git. This tracked handoff and its linked tracked docs are the portable package. Never share `.env*`, credential exports or private test fixture files.

Frontend work should use a separate feature branch, preserve backend contracts and request API additions explicitly. Document implemented features in tracked docs and local knowledge. All PRs target **develop**. Local frontend integration and browser acceptance come before any deployment; production is a separate release decision.
