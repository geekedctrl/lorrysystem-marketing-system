# Campaign Strategist

Milestone B adds a mock-first strategy workspace to the existing application. From a qualified lead detail, choose Generate campaign proposal, review saved evidence and suggested channels/assets, edit the proposal and mark strategy reviewed or rejected. This does not approve any outbound message. Existing approval/send controls remain separate.

## API
- POST /api/leads/{lead_id}/campaign-proposals: UUID idempotency_key and max_estimated_cost_usd (default 0).
- GET /api/leads/{lead_id}/campaign-proposals: saved strategy history.
- GET /api/campaign-proposals/{id}: proposal detail.
- PATCH /api/campaign-proposals/{id}: expected_version and strict strategy payload. Resets review.
- POST /api/campaign-proposals/{id}/review: expected_version, decision REVIEWED/REJECTED, notes.

A signed-in ADMIN, OPERATOR or REVIEWER generates/edits. ADMIN/REVIEWER records review. VIEWER is read-only; service credentials cannot mutate proposals. Data is scoped at API, session and PostgreSQL RLS/composite foreign-key layers.

## Preconditions and limits
Lead status QUALIFIED or READY_FOR_OUTREACH, score >=60, completed research and source observations within 30 days, active matched catalogue product. Evidence claims quote saved excerpts exactly. Contact and channel support are checked against saved sources; contact still requires human review. Strategy/copy are suggestions, not verified company facts. No current sourced channel yields an explicit review warning, not fabricated recipients.

The provider is a deterministic mock. This verifies product contracts and safety, not live AI interpretation quality. Mock generation cost is known USD0; future optional asset costs are unknown and shown Not priced. No assets are generated and no live provider is called. A global USD50 hosting/API monthly ledger and provider-side quotas remain later work before any live paid adapter.

Context fingerprints include lead, research, citations, product, contact and match. Changed context or newer research blocks review; edits increment optimistic version and invalidate review. Reusing a generation key returns its original saved proposal; use a new key to generate fresh context.

## Migration and rollback
015_campaign_proposals follows 014, adds one table with FORCE RLS, restricted grants and tenant composite references. Back up before deployment. Downgrade to 014 drops campaign proposal history; export required records first. No deployment performed during implementation.

## Verification
Offline: python api/scripts/test_campaign_strategist.py
Dashboard: python dashboard/scripts/validate_campaign_proposals.py
Disposable database: APP_ENV=workspace-test python api/scripts/validate_campaign_strategist.py
Live synthetic HTTP: APP_ENV=workspace-test python api/scripts/validate_campaign_http.py with API_BASE_URL and DASHBOARD_BASE_URL pointing to disposable instances.
CI executes these checks. Never run integration fixtures against DEV/PROD.

Further product work follows docs/ai/ROADMAP.md. Canonical engineering continuation: docs/ai/HANDOFF.md.
