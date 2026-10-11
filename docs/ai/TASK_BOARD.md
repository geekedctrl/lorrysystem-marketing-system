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

## DEV login recovery — 11 October 2026

Current work: fix/login-session-recovery, based on develop8c62de7 (user merged/deployed PR32). Stale login POSTs previously returned a bare403 and reloading repeated the invalid submission. Login now redirects303 to a fresh GET form; invalid/missing CSRF cannot reach the account API. A dedicated host-only marketing_dashboard_session cookie prevents generic-session conflicts; existing users sign in once. Initial browser mismatch cause remains unconfirmed. Public DEV GETs returned stable fresh tokens, no-store and Cloudflare DYNAMIC. See ../dashboard-login-recovery.md.

Local acceptance: ten synthetic HTTP session/login regressions, eight campaign dashboard, eight research presentation and five UX tests pass. CI includes the new login suite. User-owned .gitignore/docker-compose.yml edits are preserved. DEV deployment is authorized by the user's existing request; production and outbound sending remain outside scope. Remote CI/deployment acceptance is pending.

### DEV release acceptance — 11 October 2026, 13:23 UTC

DONE: login fix d740ed04080ae2cfb5e6900c4fe5beef7057adae deployed to DEV through successful deployment run38142917502 (https://github.com/geekedctrl/lorrysystem-deploy/actions/runs/38142917502). Both code CI runs passed: push38142704887 and PR38142725972. Public HTTPS verification passed for the dedicated cookie, invalid-token recovery to GET, actual admin sign-in/dashboard rendering and logout of the test-owned session. Cookie/password values were not logged; the temporary private verification script was deleted. Initial browser mismatch remains unconfirmed, but the reload trap is reproduced and corrected.

PR33 targets develop: https://github.com/geekedctrl/lorrysystem-marketing-system/pull/33. It remains open for the user's merge; deployment already contains the code fix. This completion record is a documentation-only follow-up. Production, accounts/passwords/keys, n8n and outbound sending were unchanged. User-owned local compose/gitignore hashes match their original values. Users should open https://dashboard-dev.obsidian.cam/login directly and sign in with the fresh form; the new cookie requires one sign-in.

## Recurring DEV session mismatch — 11 October 2026

User still sees /login?notice=session-expired on the repaired DEV runtime. Reproduced a concurrent session overwrite: hold a static response until after login and new-form generation; Starlette's unchanged-session Set-Cookie restores the old anonymous cookie and rejects the new token. Sequential verification had missed this. StableSessionMiddleware now suppresses only unchanged dashboard cookie writes, retaining signed mutation/expiry/logout behavior. Missing cookies have an actionable message; logs record only rejection reason categories. Whether this race caused the user's browser request is not yet confirmed.

Local acceptance:13 login/session HTTP tests (including a regression that failed before the fix, delayed static response, expiry, read-only cookie suppression and security gates),8 campaign dashboard,8 research and5 UX pass. See ../dashboard-login-recovery.md. Existing PR33 against develop will be updated; CI and DEV re-verification pending. User-owned local files preserved. Native frontend and production remain unchanged.

### Stable-session DEV acceptance — 11 October 2026

Code678c5d10ffb06f72458e280ca649d99feebe2a5a passed both complete CI runs38143665891 (push) and38143669343 (PR). DEV deployment38143843825 succeeded: https://github.com/geekedctrl/lorrysystem-deploy/actions/runs/38143843825. Public HTTPS checks passed: no cookie rewrite on unchanged login/static/health/dashboard, stale-token recovery, specific missing-cookie explanation, actual admin sign-in/session retention and test-session logout. All13 controlled HTTP tests also passed against the deployed image, including the delayed-response regression. The temporary private verifier was deleted.

The user has been asked to retry their affected browser. Exact browser-specific root cause remains unconfirmed until that result; the reproduced cookie-overwrite race is corrected and rejection logs now distinguish missing, invalid/expired and mismatched session state without logging sensitive values. PR33 remains open with base develop. No production, provider, outbound-send, account/password/key or user-owned compose/gitignore changes.

## DEV company discovery selection — 11 October 2026

Current branch fix/company-discovery-selection includes the unmerged PR33 session repair to preserve the running DEV baseline. Recent default-query jobs completed with zero companies despite healthy worker/provider activity. A bounded search probe confirmed directory/ranking starvation before a new official company homepage. Shared search now adds official-company wording and safe workspace-memory site exclusions; directories are removed before fetch budgeting and homepages rank first. All-fetch failures are explicit, and managed dashboard polling shows accepted results in All discoveries. Product setup targets observable customer business types. See ../company-discovery-selection.md.

Local acceptance:76 n8n tests,13 login/session checks,8 campaign dashboard and5 UX pass; discovery JS syntax passes. Refined search returns official operator sites. CI, live workflow publication, DEV app release and dashboard batch acceptance pending. User-owned gitignore/compose preserved; production and sending outside scope. New PR base develop; PR33 may be merged first to remove overlapping session changes.
