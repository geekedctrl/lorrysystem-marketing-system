# Task board

| ID | Scope | Priority | Role/owner | Branch | Dependencies | Acceptance / last verified result | Status |
|---|---|---|---|---|---|---|---|
| B-01 | Application, deployment, product audits and shared knowledge | P1 | lead + read-only specialists | codex/campaign-strategist | baseline | app9c0a3b0/deploycba785a, canonical docs and competitor gaps saved | DONE |
| B-02 | Mock strategist API and tenant persistence | P1 | backend, integrated by lead | codex/campaign-strategist | B-01 | api/app/campaign modules, migration015; 13 offline +27 DB checks passed | DONE |
| B-03 | Campaign proposal review UX | P1 | frontend, integrated by lead | codex/campaign-strategist | B-02 | dashboard templates/routes, 8 focused checks +62 actual HTTP/dashboard checks passed | DONE |
| B-04 | Regression, CI, PR and handoff | P1 | lead | codex/campaign-strategist | B-02,B-03 | 183 workspace, research/preparation/automation and n8n suites passed; PR pending | IN_PROGRESS |
| C-01 | Creative assets and budget reservation design | P2 | unassigned | future branch | B review | mock image adapter, tenant asset lifecycle, deterministic brochure, spend reservation tests; no live provider until authorized | BACKLOG |
| D-01 | Convert reviewed strategy to separately approved message actions | P2 | unassigned | future branch | B,C | immutable recipient/content approvals, existing SMTP controls, social drafts | BACKLOG |
| E-01 | Provider-neutral conversation CRM | P3 | unassigned | future branch | D | one official connector, human review, real outcome metrics | BACKLOG |
| F-01 | Optional video | P3 | unassigned | future branch | C,budget authorization | explicitly approved provider/cost experiment before enabling | BACKLOG |

## Native backend priority — 11 October 2026

The user explicitly superseded the campaign roadmap with an n8n-free backend/workers rebuild. Current branch is `rebuild/python-backend`; the earlier campaign milestone records below/above are historical context. New native product setup, discovery, bounded deeper research, professional contacts, scoring, matching, drafting and pending human approval are implemented locally in `backend/`. PostgreSQL owns stage transitions, leases, workspace boundaries, source snapshots, provider reservations and approvals. See `docs/native-preparation-workers.md` and `docs/native-worker-migration-plan.md`.

Acceptance: 30 PostgreSQL tests with synthetic providers, including six companies across two unrelated catalogs and the actual restricted worker DB role; running restricted-role HTTP API/worker smoke test also passes without provider calls. These results do not establish live provider quality. Native migrations are independent of the legacy application.

Next: dashboard integration, encrypted provider connections, authorized live calibration, separate sending parity and controlled data/account/approval migration with one-executor ownership and rollback. Existing deployed n8n remains active; no rebuild deployment, provider spend, outbound messages or automatic approval occurred. PRs target develop; production is separate. User-owned .gitignore and docker-compose.yml changes remain outside rebuild commits.

| Native task | State | Evidence / next work |
| --- | --- | --- |
| N-01 Shared stage persistence, scheduler, providers and guardrails | Implemented locally | PostgreSQL queue/ownership/atomicity/reservation checks passed |
| N-02 Discovery through pending approval | Implemented locally | 30 tests, six synthetic companies/two catalogs, restricted-role smoke |
| N-03 App connections, dashboard integration, calibration and migration | Next | Separate native database; live provider spend not authorized in this implementation |
| N-04 Sending parity and guarded executor cutover | Pending N-03 | Keep deployed n8n until parity and rollback acceptance |
