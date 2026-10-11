# Project state

## Native frontend — 11 October 2026

Backend support integration now verified: public profile/capabilities, server-side lead paging/search/current-status filters and direct detail, ADMIN catalog lifecycle, immutable human revisions with separate reviewer, and nonzero contact-search counts. Original and new support-specific browser journeys passed against actual disposable native API/PostgreSQL/workers through the local gateway8095. The initial host-port blocker below is superseded for local acceptance; process-local sessions remain unsuitable for multi-worker production. Updated portable contracts/examples and support guide are tracked.

Current isolated frontend branch: `geekedctrl/redesign-frontend`. Native Python backend priority supersedes the older campaign roadmap for this task. Native backend source is in the separate `rebuild/python-backend` checkout (`721a44f`); its handoff and OpenAPI snapshot have been copied into this branch. See `../native-frontend.md` for implemented UI, test scope, session architecture and backend dependencies. `dashboard/app/native.py` is an independent frontend entry point; legacy `app.main` remains unchanged. Windows host access to native port8020 is refused despite a successful container-internal health check; actual native-backend browser integration remains pending.

Application baseline9c0a3b0 develop verified; current work on codex/campaign-strategist.
Existing code and local synthetic regressions verify workspace auth/RLS, bounded research and n8n worker leases, scoring/product matching, preparation, approval snapshots and controlled sending architecture. Live deployment and research quality are not implied by local tests.
Campaign proposals implemented: deterministic mock inference, strict cited claims, conditional supported channels/assets, unknown future costs, persisted RLS strategy record, idempotency, context fingerprint, versions and human strategy review/rejection. Dashboard supports generation/history/evidence/edit/review. No outbound actions or paid calls created.
Global USD50 hosting/API monthly ledger, live LLM adapters, creative asset generation, unified inbox and video remain later milestones. Free-form copy is unverified until human review. See ../campaign-strategist.md and ROADMAP.md.
