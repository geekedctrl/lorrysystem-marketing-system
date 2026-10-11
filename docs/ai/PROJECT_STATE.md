# Project state

## Native frontend — 11 October 2026

Backend support integration now verified: public profile/capabilities, server-side lead paging/search/current-status filters and direct detail, ADMIN catalog lifecycle, immutable human revisions with separate reviewer, and nonzero contact-search counts. Original and new support-specific browser journeys passed against actual disposable native API/PostgreSQL/workers through the local gateway8095. The initial host-port blocker below is superseded for local acceptance; process-local sessions remain unsuitable for multi-worker production. Updated portable contracts/examples and support guide are tracked.

Current isolated frontend branch: `geekedctrl/redesign-frontend`. Native Python backend priority supersedes the older campaign roadmap for this task. Native backend source is in the separate `rebuild/python-backend` checkout (`721a44f`); its handoff and OpenAPI snapshot have been copied into this branch. See `../native-frontend.md` for implemented UI, test scope, session architecture and backend dependencies. `dashboard/app/native.py` is an independent frontend entry point; legacy `app.main` remains unchanged. Windows host access to native port8020 is refused despite a successful container-internal health check; actual native-backend browser integration remains pending.

Application baseline9c0a3b0 develop verified; current work on codex/campaign-strategist.
Existing code and local synthetic regressions verify workspace auth/RLS, bounded research and n8n worker leases, scoring/product matching, preparation, approval snapshots and controlled sending architecture. Live deployment and research quality are not implied by local tests.
Campaign proposals implemented: deterministic mock inference, strict cited claims, conditional supported channels/assets, unknown future costs, persisted RLS strategy record, idempotency, context fingerprint, versions and human strategy review/rejection. Dashboard supports generation/history/evidence/edit/review. No outbound actions or paid calls created.
Global USD50 hosting/API monthly ledger, live LLM adapters, creative asset generation, unified inbox and video remain later milestones. Free-form copy is unverified until human review. See ../campaign-strategist.md and ROADMAP.md.

## Native backend priority — 11 October 2026

The user explicitly superseded the campaign roadmap with an n8n-free backend/workers rebuild. Current branch is `rebuild/python-backend`; the earlier campaign milestone records below/above are historical context. New native product setup, discovery, bounded deeper research, professional contacts, scoring, matching, drafting and pending human approval are implemented locally in `backend/`. PostgreSQL owns stage transitions, leases, workspace boundaries, source snapshots, provider reservations and approvals. See `docs/native-preparation-workers.md` and `docs/native-worker-migration-plan.md`.

Acceptance: 30 PostgreSQL tests with synthetic providers, including six companies across two unrelated catalogs and the actual restricted worker DB role; running restricted-role HTTP API/worker smoke test also passes without provider calls. These results do not establish live provider quality. Native migrations are independent of the legacy application.

Next: dashboard integration, encrypted provider connections, authorized live calibration, separate sending parity and controlled data/account/approval migration with one-executor ownership and rollback. Existing deployed n8n remains active; no rebuild deployment, provider spend, outbound messages or automatic approval occurred. PRs target develop; production is separate. User-owned .gitignore and docker-compose.yml changes remain outside rebuild commits.

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
