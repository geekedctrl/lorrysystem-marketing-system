# Project state

Application baseline9c0a3b0 develop verified; current work on codex/campaign-strategist.
Existing code and local synthetic regressions verify workspace auth/RLS, bounded research and n8n worker leases, scoring/product matching, preparation, approval snapshots and controlled sending architecture. Live deployment and research quality are not implied by local tests.
Campaign proposals implemented: deterministic mock inference, strict cited claims, conditional supported channels/assets, unknown future costs, persisted RLS strategy record, idempotency, context fingerprint, versions and human strategy review/rejection. Dashboard supports generation/history/evidence/edit/review. No outbound actions or paid calls created.
Global USD50 hosting/API monthly ledger, live LLM adapters, creative asset generation, unified inbox and video remain later milestones. Free-form copy is unverified until human review. See ../campaign-strategist.md and ROADMAP.md.

## Native backend priority — 11 October 2026

The user explicitly superseded the campaign roadmap with an n8n-free backend/workers rebuild. Current branch is `rebuild/python-backend`; the earlier campaign milestone records below/above are historical context. New native product setup, discovery, bounded deeper research, professional contacts, scoring, matching, drafting and pending human approval are implemented locally in `backend/`. PostgreSQL owns stage transitions, leases, workspace boundaries, source snapshots, provider reservations and approvals. See `docs/native-preparation-workers.md` and `docs/native-worker-migration-plan.md`.

Acceptance: 30 PostgreSQL tests with synthetic providers, including six companies across two unrelated catalogs and the actual restricted worker DB role; running restricted-role HTTP API/worker smoke test also passes without provider calls. These results do not establish live provider quality. Native migrations are independent of the legacy application.

Next: dashboard integration, encrypted provider connections, authorized live calibration, separate sending parity and controlled data/account/approval migration with one-executor ownership and rollback. Existing deployed n8n remains active; no rebuild deployment, provider spend, outbound messages or automatic approval occurred. PRs target develop; production is separate. User-owned .gitignore and docker-compose.yml changes remain outside rebuild commits.
