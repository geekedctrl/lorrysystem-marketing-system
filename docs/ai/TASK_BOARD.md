# Task board

## Native frontend — 11 October 2026

| ID | Scope | State |
| --- | --- | --- |
| UI-N01 | Opaque server sessions, native bridge, workspace/role shell | Implemented; synthetic BFF checks |
| UI-N02 | Setup/discovery/preparation/contact/qualification/approval/operations | Implemented against native handoff |
| UI-N03 | Synthetic browser acceptance, responsive screenshots, docs | Local validation; see native-frontend.md |
| UI-N04 | Disposable actual native-worker browser integration | DONE locally through gateway8095; original and support-control journeys passed |
| UI-N06 | Profile, paging/detail, catalog lifecycle, human revision and contact-count adapters | DONE; eight BFF groups, expanded synthetic browser and actual support browser passed |
| UI-N05 | Production sessions, missing API parity, migration and release | Backend/release dependencies; no deployment |

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

## Native frontend backend support — 11 October 2026

Implemented BE-01–BE-06 locally on rebuild/native-frontend-support, based on merged PR #29. See ../native-frontend-backend-support.md for new typed contracts/auth capabilities, direct/paginated leads, immutable human revision and separate reviewer, soft catalog lifecycle/versioning, partial setup semantics and frontend adapter requirements. Independent compose.native-integration.yml provides actual restricted API/DB/workers plus the frontend owner's read-only native UI. Synthetic external providers only; worker-loop discovery scheduling gap fixed.

Verification: 37 PostgreSQL tests passed; actual API/BFF/worker two-product/contact/failure/retry/role/isolation checks passed; actual headless Edge product-form/preparation/review/approval and tablet/mobile checks passed; actual restricted API revision/lifecycle checks passed. Windows Docker forwarding remains defective, with a tested localhost-only gateway fallback at8095; frontend-to-API internal networking works. No frontend-owned files, deployed executor, paid providers or sending changed. New BFF allowlists/adapters and nonzero unavailable-search count rendering remain frontend-owner work. BE-07–11 and shared production sessions remain later milestones. New changes local, not pushed/deployed; PR base develop.


## Real DEV discovery diagnosis � 11 October 2026

User-authorized real discovery test completed against the deployed legacy DEV application through an SSH loopback forward. Shared n8n discovery was patched for visible HTML punctuation, explicit all-candidate evidence rejection and literal-node provider usage collection. A real Soon Lee Transport lead was accepted and rendered; research was queued automatically. All 73 n8n JavaScript tests pass. See ../dev-discovery-acceptance.md. Existing native rebuild remains a separate runtime; no app deployment, sending or cutover performed. Local follow-up branch fix/dev-discovery-evidence; native frontend support fd6c5a3 was previously pushed. PR base remains develop.
