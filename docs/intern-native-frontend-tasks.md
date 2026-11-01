# Intern Assignment: Native Dashboard Connections UX

## Objective

Improve the native dashboard's read-only Connections page using the existing native API and BFF. This is the intern's first, bounded frontend assignment. Work is limited to presentation and synthetic frontend validation; the project owner maintains the Python backend and workers separately.

## Required boundaries

- Do not edit Python backend or worker implementation: `backend/`, `api/`, `database/`, migrations, or worker/service logic.
- Do not change API contracts or add backend endpoints. If an existing endpoint is missing or insufficient, document the gap and stop at a frontend-safe state.
- Do not touch deployment configuration, CI release workflows, secrets, live DEV/production data, providers, email sending, executor ownership, or migration/cutover behavior.
- Use synthetic fixtures and local validation only. Do not call paid providers or send messages.
- Preserve organization/workspace isolation, server-side opaque sessions, CSRF protections, escaped server content, and human approval gates.
- Keep changes on a dedicated feature branch. Submit a reviewable PR; do not merge or deploy.

## Allowed implementation area

Primary files:

- `dashboard/app/native.py` — BFF session and allowlisted route adapters only, if needed to connect existing API routes.
- `dashboard/app/static/native.js`
- `dashboard/app/static/native.css`
- `dashboard/app/templates/native.html`
- Frontend validation scripts under `dashboard/scripts/` and focused frontend tests only.

Ask the project owner before editing any file outside these areas. Do not modify `docs/ai/`; the project owner maintains it.

## Assignment — Read-only Connections UX

Make existing provider-connection status easier to understand without changing provider configuration or making provider calls.

### Requirements

- Present the existing connection states distinctly: configured, unverified, unavailable, disabled, and any additional status returned by the current API. Current source returns `configured`, `unverified`, and `unavailable` for model/search, and `disabled`, `verified`, or `unverified` for provider drafts.
- Explain whether a connection is available for use without implying that it was tested or verified.
- Keep secret values out of the browser and never echo submitted secret fields after a response or error.
- Do not add enable, verify, test, or paid-provider actions. Do not change connection state.
- Provide an actionable empty state that points workspace admins to the approved configuration process without exposing credentials.

### Acceptance checklist

- [ ] All states returned by existing contracts have clear, distinct labels and descriptions, including automation and sender status if shown on this page.
- [ ] Unknown future states render safely and do not break the page.
- [ ] No secret value appears in DOM, browser storage, logs, or error text.
- [ ] No action sends a request to a provider or changes provider state; this assignment is read-only.
- [ ] Synthetic tests cover each state, API unavailable, and unknown state.
- [ ] Responsive and keyboard checks pass.

## Follow-on backlog — not part of this assignment

The following ideas are reserved for separate assignments after owner review of the Connections UX PR. Do not include them in this branch or PR.

### Job review and retry UX

Clarify failed jobs and contact-review stops, and expose only safe retry actions already supported by the native API.

### Requirements

- Explain job status and failure/review reason in product language; keep raw provider/API details out of the main view unless already safely exposed and escaped.
- Show whether a retry is available and which role can request it.
- Use existing retry routes only; honor pause/automation state and API authorization.
- Preserve explicit human review requirements. Never auto-accept contacts, approve drafts, or send messages.
- Show pending, success, and failure feedback; prevent duplicate submissions while a request is in flight.
- Ensure workspace switching invalidates old job data and late responses.

### Acceptance checklist

- [ ] Failed, retryable, non-retryable, and needs-review states are understandable.
- [ ] Retry action appears only when supported and is guarded against duplicate submission.
- [ ] Existing role and paused-automation rules are reflected in the UI; server errors remain clear.
- [ ] Retry does not bypass contact review, candidate acceptance, draft approval, or send approval.
- [ ] Synthetic tests cover statuses, retry outcomes, role denial, paused state, duplicate click, and workspace switching.
- [ ] Keyboard and narrow/mobile layout checks pass.

### Import preview UI (synthetic only)

Build a frontend preview and validation experience for workspace imports without implementing a real import or migration.

### Requirements

- Use a local synthetic fixture or mocked response; do not connect to production or live workspace data.
- Display parsed rows, field mapping, validation errors, duplicate warnings, and a clear summary before any hypothetical commit step.
- Do not add a functional import/commit API call. The final action must remain a disabled preview-only control with an explanation until the owner supplies an approved backend contract.
- Preserve organization/workspace context and make the selected destination obvious.
- Escape imported/untrusted values and handle malformed/oversized fixture input safely.

### Acceptance checklist

- [ ] Preview covers valid rows, missing required fields, duplicates, and malformed input.
- [ ] No request can create, modify, or migrate workspace records.
- [ ] Untrusted values are escaped and do not render as executable markup.
- [ ] Preview identifies the selected organization/workspace and reports row counts.
- [ ] Synthetic tests cover valid, invalid, duplicate, empty, and malformed input.
- [ ] Keyboard and narrow/mobile layout checks pass.

## Definition of done

- [ ] Implement only the read-only Connections UX in a small, reviewable PR.
- [ ] Existing native frontend validation passes: `.venv/Scripts/python dashboard/scripts/validate_native_frontend.py --browser` (or document a specific environment blocker).
- [ ] Add focused synthetic frontend coverage for new behavior; do not run against live providers or accounts.
- [ ] No backend/worker/API-contract/deployment files changed.
- [ ] No secrets, real invitations, real prospect data, provider calls, or outbound messages in fixtures or logs.
- [ ] PR description lists files changed, checks run, known limitations, and screenshots for visible UX changes.
- [ ] Request owner review before any merge, publication, deployment, or live test.

## Bitrix task

**Title:** Improve Native Dashboard Connections Page (Frontend Only)

**Description:** Implement only the read-only Connections UX assignment in this document using existing native API/BFF behavior. Clearly explain connection states without implying verification, keep secrets out of the browser, and add synthetic frontend coverage. Do not edit Python backend/workers, API contracts, deployment/release files, or `docs/ai/`. Do not touch live DEV/production data, enable or test providers, send email, merge, or deploy. Work on a dedicated branch and submit a PR for owner review. If the page needs a new endpoint or contract, document the gap and stop before backend changes.

**Bitrix checklist:**

- [ ] Read this assignment and confirm the frontend-only boundaries.
- [ ] Create a dedicated feature branch.
- [ ] Implement read-only Connections UX and synthetic coverage.
- [ ] Confirm no backend, worker, API-contract, migration, deployment, or `docs/ai/` files changed.
- [ ] Run native frontend validation and record the result.
- [ ] Attach screenshots for visible UI changes.
- [ ] Open a PR with summary, test results, and known limitations.
- [ ] Wait for owner review; do not merge or deploy.
