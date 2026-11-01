# Intern Task Allocations — Native Dashboard

These are proposed, independent frontend assignments for the intern. The Connections UX, job retry UX, team settings UX, and synthetic import preview from the earlier brief are already present in the latest `develop` branch; do not repeat those tasks.

## Shared boundaries

- Work from the latest `develop` in a dedicated feature branch, one assignment per PR.
- Limit implementation to native dashboard presentation and synthetic frontend tests. Do not edit backend/workers, API contracts, migrations, deployment or release workflows, secrets, or `docs/ai/`.
- Use local synthetic fixtures only. Do not access live DEV/production data, call providers, send email, or change workspace records.
- Preserve organization/workspace isolation, CSRF and session behavior, HTML escaping, role permissions, and explicit human review/approval gates.
- Use existing API/BFF behavior only. If a task requires a new endpoint or a change in product policy, document the gap and ask the owner before proceeding.
- Open a reviewable PR with checks, limitations, and screenshots for visible changes. Do not merge or deploy.

## Task INTERN-UI-01 — Improve Dashboard Accessibility and Keyboard Navigation

### Description

Audit and make focused accessibility improvements to the Overview and Leads pages. Keep the current visual design and behavior; address concrete keyboard, focus, semantic markup, responsive table, and assistive-technology issues rather than undertaking a redesign. Use existing design tokens and reduced-motion preferences where relevant.

### Checklist

- [ ] Review Overview and Leads at desktop and narrow/mobile widths using keyboard-only navigation.
- [ ] Ensure interactive controls have meaningful accessible names, visible focus, and logical focus order.
- [ ] Check heading hierarchy, landmarks, table captions/headers, status announcements, and error messaging.
- [ ] Verify no horizontal page overflow at the tested narrow viewport; make dense tables usable without hiding essential data.
- [ ] Respect `prefers-reduced-motion` for any animation touched.
- [ ] Add synthetic browser checks for the fixed issues and relevant keyboard paths.
- [ ] Run the native frontend validation command and record results.
- [ ] Include before/after screenshots and list any findings intentionally deferred.

## Task INTERN-UI-02 — Clarify Leads and Discovery Empty, Loading, and Error States

### Description

Make Leads and Discovery screens understandable when there is no data, a request is loading, or an existing request fails. Provide concise, role-aware next steps using current routes and controls only. Do not introduce new retry semantics, API calls, or changes to candidate acceptance and review.

### Checklist

- [ ] Inspect the existing Leads and Discovery loading, empty, unavailable, and request-error states.
- [ ] Distinguish “no records yet” from “data could not be loaded”; do not present failures as empty results.
- [ ] Show a useful next step only when it is supported by the current role and existing UI/API behavior.
- [ ] Keep raw backend/provider errors out of user-facing copy unless already intentionally exposed and safely escaped.
- [ ] Preserve candidate evidence review and explicit accept/reject decisions; do not add automatic acceptance.
- [ ] Ensure workspace/organization switching clears stale screen data and ignores late responses.
- [ ] Add synthetic tests for empty, loading, failure, role-restricted, and workspace-switch cases.
- [ ] Verify responsive and keyboard behavior; run native frontend validation and attach screenshots.

## Task INTERN-UI-03 — Add Client-Side Filters to the Existing Operations Activity View

### Description

Make the Operations activity view easier to scan by adding filters over records already loaded by the current page. Candidate filters may include job type and status, provided those values exist in the current response. Clearly label that filtering applies to the currently loaded activity; do not imply it searches complete history or add pagination/API behavior.

### Checklist

- [ ] Confirm the exact fields and loaded-record limit from the current frontend/BFF source before designing filters.
- [ ] Add accessible filters for only the supported loaded fields, plus a clear/reset action.
- [ ] Keep pause/resume and retry controls governed by existing role, job-state, and automation rules.
- [ ] Show a distinct no-activity state and a distinct no-matching-records state.
- [ ] Escape all displayed record content and avoid showing secrets or unsafe raw provider details.
- [ ] Reset filters and invalidate old results when organization/workspace context changes.
- [ ] Add synthetic tests for combined filters, reset, no matches, role restrictions, and context switching.
- [ ] Verify narrow/mobile and keyboard usability; run native frontend validation and attach screenshots.

## Definition of done for each task

- [ ] Only the assigned task is included in the branch/PR.
- [ ] No backend, worker, API-contract, migration, deployment, or release-workflow changes are present.
- [ ] Tests use synthetic data and do not make provider, email, or live-account requests.
- [ ] Native frontend validation passes, or a specific environment blocker is documented.
- [ ] PR describes scope, changed files, test results, screenshots, and known limitations.
- [ ] Wait for owner review; do not merge or deploy.
