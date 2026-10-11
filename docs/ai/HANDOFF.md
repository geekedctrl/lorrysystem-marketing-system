# LorrySystem AI Development Handoff

## Native frontend continuation — 11 October 2026

Latest: backend BE-01–06 fixes consumed from `rebuild/native-frontend-support`. Frontend profile/pagination/detail/lifecycle/revision adapters implemented and integer contact-search count fixed. Eight BFF groups and expanded synthetic browser checks pass. Both original and support-specific actual browser journeys passed against disposable native API/PostgreSQL/workers through localhost8095. The older connection-blocked statement below is superseded. See `docs/native-frontend-backend-support.md` and `docs/native-frontend.md`. Production session storage and BE-07–11 remain separate work; no release or real-provider activity.

Backend follow-up task brief: [backend-native-frontend-handoff.md](../backend-native-frontend-handoff.md). It prioritizes actual native integration, typed contracts/capabilities, detail/lists, revisions and catalog lifecycle, with ownership and acceptance requirements for the backend agent.

User authorized implementation of the native frontend plan on `geekedctrl/redesign-frontend`. Current task follows the native Python backend handoff, superseding the historical campaign next steps below. Independent entry point `dashboard/app/native.py`, native HTML/CSS/JS, copied frontend handoff/OpenAPI, and synthetic BFF/browser validation have been added. Read `docs/native-frontend.md` for run commands, behavior, limitations and verification. Do not execute the historical push/merge steps below as instructions for this task.

Backend checkpoint721a44f is in the separate `rebuild/python-backend` checkout. Only read-only source/reference inspection was performed there. Native container-internal `/health` succeeds; Windows localhost8020 refuses connections. Actual backend/worker/browser integration remains pending. Sessions are process-local for single-process local preview; shared production session storage is a release dependency. No provider calls, emails, deployment, push or merge performed.

## Last Updated
2026-10-10T10:28:00+08:00

## Project Goal
Evolve the existing product; Milestone B delivers mock campaign strategy from qualified evidence-backed prospects to saved proposals and human review.

## Repository State
Application https://github.com/geekedctrl/lorrysystem-marketing-system — codex/campaign-strategist, base9c0a3b0f03306d399ba9ee76ab14a8be37e7ed09. Initial knowledge checkpoint9540786. Implementation currently uncommitted and about to be checkpointed; run git status --short and git rev-parse HEAD.
Deployment https://github.com/geekedctrl/lorrysystem-deploy — main,cba785acbb4da43a135da4a6bc06d1bfb94cda40 inspected through API; no modifications.

## Current Milestone
B — mock Campaign Strategist; feature code and local verification complete, PR/remote CI pending.

## Current Task
B-04, lead, IN_PROGRESS: checkpoint and PR to develop.

## Completed Work
Three bounded audits, shared vendor-neutral docs, API/migration015 and dashboard review UX.13 offline tests,27 PostgreSQL checks,62 actual HTTP/dashboard checks,8 focused dashboard tests. Existing workspace183 checks, research, pipeline, quality, automation, n8n70, presentation8 and UX5 passed. See TEST_STATUS.md.

## Incomplete Work
Push implementation and open PR; remote CI results. Live providers, creative generation, global budget ledger, multichannel conversion, CRM and video are later milestones. Contact verification metadata and browser viewport visual QA remain limitations.

## Changed Files
api/app auth/router/model/schema/service registrations; api/scripts campaign suites and workspace RLS count; database/migrations/versions/015_campaign_proposals.py; dashboard/app routes, workspace roles, templates and portable import temp path; dashboard/scripts/validate_campaign_proposals.py; .github/workflows/ci.yml; README.md; docs/campaign-strategist.md; AGENTS.md and docs/ai.

## Architecture Decisions
DECISIONS.md ADR001–004. Proposal review is not outbound action approval. Mock provider constrained in DB. Unknown future asset cost is null; generation cost0 is known. Context/optimistic versions guard review and edits.

## Test Results
TEST_STATUS.md gives commands/environment/caveats. WindowsPython3.14 venv, PostgreSQL17 disposable container lorry-campaign-test-8882 at localhost55432/campaign_test, API8012/dashboard8092. No existing data volumes. Synthetic-only tests. No actual search/model/send.

## Blockers
No local implementation blocker. Git shared metadata requires sandbox escalation. Remote CI not executed yet. USD50 total monthly policy is not implemented; live paid adapters must wait for cost controls and authorization.

## Next Steps
1. Commit reviewed implementation, push codex/campaign-strategist and create PR targeting develop.
2. Record PR and remote CI result; stop task-owned local services/container after testing.
3. Review/merge only with user authorization; then plan milestone C mock asset lifecycle and budget reservations.

## Safety Notes
No merging, DEV/PROD deployment, real prospect contact, paid provider calls, account credentials or infrastructure changes authorized. Feature branch does not trigger DEV deployment. Free-form copy remains an unverified human-reviewed suggestion; social affiliation remains hypothesis. Migration downgrade drops proposal history, requiring backup/export.

## Handoff Readiness
PARTIAL — verified code local; remote checkpoint/PR pending.

## Native backend priority — 11 October 2026

The user explicitly superseded the campaign roadmap with an n8n-free backend/workers rebuild. Current branch is `rebuild/python-backend`; the earlier campaign milestone records below/above are historical context. New native product setup, discovery, bounded deeper research, professional contacts, scoring, matching, drafting and pending human approval are implemented locally in `backend/`. PostgreSQL owns stage transitions, leases, workspace boundaries, source snapshots, provider reservations and approvals. See `docs/native-preparation-workers.md` and `docs/native-worker-migration-plan.md`.

Acceptance: 30 PostgreSQL tests with synthetic providers, including six companies across two unrelated catalogs and the actual restricted worker DB role; running restricted-role HTTP API/worker smoke test also passes without provider calls. These results do not establish live provider quality. Native migrations are independent of the legacy application.

Next: dashboard integration, encrypted provider connections, authorized live calibration, separate sending parity and controlled data/account/approval migration with one-executor ownership and rollback. Existing deployed n8n remains active; no rebuild deployment, provider spend, outbound messages or automatic approval occurred. PRs target develop; production is separate. User-owned .gitignore and docker-compose.yml changes remain outside rebuild commits.

## Frontend handoff — 11 October 2026

User requested a shareable requirements and source-location brief for a separate frontend developer. See [frontend-native-backend-handoff.md](../frontend-native-backend-handoff.md) and [OpenAPI snapshot](../contracts/native-backend-openapi.json). The handoff maps native screen requirements, roles, request/result contracts, UI states, existing design references and missing backend support. OpenAPI was exported from the running native API; untyped responses still require the documented/source response map. Implementation checkpoint721a44f and the handoff are being published together as the next PR targeting develop; the foundation was already merged in PR #28. No frontend implementation or executor cutover occurred. The replacement backend remains an independent runtime, not the currently deployed executor.

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

### Exact discovery excerpts — 11 October 2026

Initial corrected default-query batches a1a4bdf0 and ca5f5ec8 reached official KGW/Hock Cheong pages but failed DISCOVERY_EVIDENCE_REJECTED. Diagnostic execution21159 confirmed that the model stitched nonadjacent Hock Cheong passages into one quote. Temporarily enabled child execution saving was restored to none immediately after collection. New extraction selects supplied source/excerpt IDs; the application resolves exact fetched text/URL, while name, identity, ICP, confidence and quotation gates remain. Invalid cross-page/unknown IDs cannot create a lead.79 n8n tests pass. Follow-up CI/publication and final live batch pending; initial search/UI release3066c2e already deployed in DEV through38145264438. PR34 is open against develop and includes PR33 session changes. No production changes or sending.


### Company discovery DEV acceptance — 11 October 2026

Code `8b9d162dfdcc6301404bbbe0060399703a9f213b` passed full push CI `38145984359` and PR CI `38145987247`. DEV deployment [38146226265](https://github.com/geekedctrl/lorrysystem-deploy/actions/runs/38146226265) succeeded. Discovery and setup child workflows were published through the DEV n8n API with existing named credentials and workspace/lease headers preserved; the dispatcher resumed. All three workflows are active with current published versions and execution saving set to `none`.

A normal public-HTTPS admin login and LorrySystem workspace switch submitted the unchanged dashboard default query with a target of one company. Discovery job `960988f3-ffcb-4835-80e3-4084f9b2d07c` completed with `COMPANIES_ACCEPTED`, one new candidate and one accepted lead: **Hock Cheong**, `hockcheong.com.my`, lead `53f3592e-b375-4f7b-bb49-5c46be4d78d2`. A separate normal HTTP session verified the company in `/leads`, its detail page and `/discovered-leads?status=ALL`. Both test sessions logged out. The batch used one search, two fetches and one model call (4,932 input / 137 output tokens); recorded monetary cost is unavailable.

Follow-up research automatically ran and stopped at `NEEDS_REVIEW` / `SUPPORTED_CONTACT_REQUIRED`; discovery succeeded, but outreach preparation is not claimed complete. No outreach was approved or sent. The task-created retained diagnostic execution `21159` and temporary credential-bearing verifiers/raw diagnostic payload were removed after verification. User-owned compose/gitignore contents remain intact. PR [34](https://github.com/geekedctrl/lorrysystem-marketing-system/pull/34) targets `develop` and includes unmerged PR33's session repair to preserve the DEV baseline. Production and native-worker rollout are unchanged.


### Discovery rebuild discussion — 11 October 2026

User correction: discovered companies must await explicit human acceptance; automatic acceptance is no longer the desired policy. Both deployed `api/app/routers/automation.py` candidate ingestion and native `backend/marketing_backend/pipeline.py` discovery finalization currently create official leads automatically and schedule research. Both require revision before claiming manual-review behavior. The preceding successful one-company DEV test proves that one batch worked, not that discovery is broadly reliable.

Discussed direction: native Python discovery workers collect website evidence and use the existing xKiro adapter for catalog/ICP assessment. Reuse the existing queue/workspace/provider infrastructure. Proposed flow: search → bounded company-site crawl/extraction → evidence-backed assessment → candidate inbox → explicit Accept/Reject → accepted lead and research → remaining preparation → human outreach approval. Ordinary HTTP fetching and structured extraction first, browser rendering as a controlled fallback. Candidate-level failures, retryable discovery memory and visible stage counts are proposed reliability work. Search-provider choice and implementation scope remain discussion items; this entry changes documentation only and does not disable running workflows or alter records.


## Native discovery with manual review — 11 October 2026

Implemented on rebuild/manual-discovery: Brave website finding, guarded Python company crawling, Trafilatura extraction, optional guarded Playwright rendering and per-company xKiro assessments with numbered evidence excerpts. Discovery persists review candidates only. Explicit human Accept creates the lead/research run atomically and idempotently; Reject preserves the decision; targeted Reassess and retryable memory cover unavailable companies. Workspace RLS, catalog staleness, concurrent domain duplicate checks and native-worker lead INSERT denial guard the transition. Native dashboard/BFF adds candidate review, evidence, filters/paging and stage counts. Legacy ingestion, contract/export and summaries now also require human acceptance in source. See ../native-lead-discovery.md and the refreshed OpenAPI.

Acceptance: 50 PostgreSQL/backend tests, including actual Chromium network isolation, empty JavaScript shells and malformed links; nine BFF groups and the synthetic browser; actual local browser/product form/BFF/restricted API/native worker manual acceptance; actual two-product native API/worker acceptance; legacy shared automation regression; 79 n8n checks; 13 login/session and five UX checks. Providers are synthetic. Local disposable projects discovery-review-test and discovery-legacy-test isolate fixtures. Live provider calibration/native DEV cutover and coordinated legacy n8n publication remain release work; no deployed executor changed and no outbound messages sent. Existing PR #33/#34 are now merged; latest develop `9e74818` adds separate frontend CSS. Preserve user-owned gitignore/compose; PR base develop.


Release checkpoint: implementation commit `bec7684`, integrated latest develop `9e74818` with merge `cf90bb9`; pushed branch `rebuild/manual-discovery`. Draft PR #36 targets develop: https://github.com/geekedctrl/lorrysystem-marketing-system/pull/36 . Keep draft until coordinated legacy guard/API publication or native cutover is ready; DEV has not been changed. GitHub CI is running. Local fixture projects `discovery-review-test` and `discovery-legacy-test`, their disposable volumes and the port 8098 gateway were removed after verification; pre-existing local stacks remain untouched. User-owned root compose/gitignore hashes remain unchanged and those edits are excluded.
