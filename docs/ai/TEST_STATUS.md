# Test status — 10 October 2026 MYT

## Native frontend — 11 October 2026

Latest backend-support adaptation: eight BFF groups and expanded synthetic browser suite passed with profiles, validated query forwarding, paging/search/older detail, nonzero unavailable-search counts, catalog lifecycle and revision/separate-review controls. `backend/scripts/validate_native_browser.py` from the backend support checkout passed through actual BFF/API/PostgreSQL/workers using private disposable fixture accounts at localhost8095. `dashboard/scripts/validate_native_support_browser.py` additionally passed actual profile/cursor/search/detail, fresh preparation, requested changes, sourced immutable revision, disabled editor approval, another reviewer's approval (`sent:false`), catalog deactivation/reactivation/resume and persistent stale approval. Screenshots under ignored `tmp/native-actual-browser` and `tmp/native-support-browser`. API was not mocked for these two runs. The earlier actual-integration-unverified statement below is superseded. No live providers or real messages; fixture credentials remain ignored.

Local implementation on `geekedctrl/redesign-frontend` uses the separate native backend handoff/OpenAPI. Executed `dashboard/scripts/validate_native_frontend.py --browser` with Python3.14 and headless local Edge: six BFF groups passed; synthetic browser journey passed across two unrelated workspaces and all four roles. Includes wizard partial-save/idempotent retry, contact continuation, approval without sending, stale disabled approval, pause/resume, failed-job retry, failed-form retention, historical failed/current successful preparation, responsive desktop/tablet/mobile, keyboard tabs/drawer, theme and provider-text escaping. Screenshots saved under ignored `tmp/native-ui-review`; desktop overview and mobile lead list visually inspected.

Backend container-internal native `/health` returns ok; Windows host request to localhost8020 fails with connection refused. Actual native DB/worker/frontend end-to-end execution remains unverified. No provider/SMTP requests or existing database mutations were performed. Browser acceptance uses in-process synthetic API responses, not a running worker. Native frontend CI checks added; remote CI not run.

Baseline application 9c0a3b0; current changes on codex/campaign-strategist. Local Windows Python3.14 .venv; PostgreSQL17 Docker container lorry-campaign-test-8882, DB campaign_test on 127.0.0.1:55432. Synthetic credentials only, no existing data volume. API localhost8012; dashboard localhost8092.

Executed:
- node --test integrations/n8n/*.test.js — 70 passed.
- .venv/Scripts/python.exe api/scripts/test_campaign_strategist.py — 13 passed, final source and contact citation hardening included.
- .venv/Scripts/python.exe api/scripts/validate_campaign_strategist.py — 27 passed in final lead rerun.
- .venv/Scripts/python.exe dashboard/scripts/validate_campaign_proposals.py — 8 passed.
- .venv/Scripts/python.exe dashboard/scripts/validate_research_presentation.py — 8 passed.
- .venv/Scripts/python.exe dashboard/scripts/validate_ux_states.py — 5 passed.
- Alembic API upgrade with explicit script/version locations — all migrations001 through015 passed on empty disposable DB.
- api/scripts/validate_preparation_quality.py — six synthetic company/two-product scenarios passed, no live providers/sends.
- api/scripts/validate_product_automation.py — passed with PYTHONIOENCODING=utf-8; initial run failed only printing arrow under cp1252 after successful assertions.
- api/scripts/validate_workspace_research.py — passed, including dashboard and worker lifecycle.
- api/scripts/validate_lead_pipeline.py — passed, including dashboard, stale context and approvals.
- api/scripts/validate_workspaces.py —183 checks passed after extending expected RLS table count22→23 for new campaign table. Earlier attempts lacked test root key, then hit stale count assertion; both corrected.
- compileall api/app dashboard/app database/migrations, CI YAML parse, git diff --check — passed.

api/scripts/validate_campaign_http.py —62 checks passed against running API/dashboard in final lead rerun. CI executes the new suites; remote CI pending PR. No live model/search/SMTP calls. No viewport/browser visual check yet. Runtime AI quality, provider terms/pricing and production deployment remain unverified.


## Native worker acceptance — 11 October 2026

Independent Docker project `marketing-rebuild`, PostgreSQL17 `marketing_rebuild_test`, native migrations through005_job_run_ownership. Thirty integration tests passed with synthetic providers, including six companies across transport/accounting catalogs, actual restricted worker role, source-backed contact continuation, contact-search refresh, atomic rollback/idempotency, pause/context/ownership guards, conservative provider reservations and provider error handling. No paid provider calls or outbound messages.

Command: `docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml --profile test run --rm --build backend-test`. Running HTTP API/worker smoke command uses the same Compose invocation with backend-smoke. Its missing-provider checks verify both manual and native queues using their actual restricted database roles, removing only the explicit smoke fixtures.

Synthetic results do not validate real provider prose/coverage, dashboard migration, sending or DEV cutover. Legacy test records remain historical.

## Native frontend support acceptance — 11 October 2026

- `docker compose --env-file .env.backend-local -p marketing-rebuild -f compose.backend.yml --profile test run --rm --build backend-test`: 37 tests passed in 19.589s, isolated marketing_rebuild_test.
- `docker compose --env-file .env.native-integration-local -p native-acceptance -f compose.native-integration.yml --profile test run --rm --no-deps --build native-check`: actual restricted HTTP API/BFF/DB/worker acceptance passed for two products, contacts, retry, pause and isolation. External providers/evidence synthetic, reservation cost0.
- `tmp/native-browser-venv/Scripts/python.exe backend/scripts/validate_native_browser.py --fixtures tmp/native-acceptance-accounts.json`: actual headless Edge acceptance passed through localhost8095 gateway and real native backend; four roles and tablet/mobile. Earlier test failures were resolved: idle scheduling, fixture volume ownership, synthetic failure replay, async browser wait and Windows console ASCII output.
- `... native-check python -m tests.native_support_check`: actual restricted API capabilities/paging/revision/lifecycle passed; separate reviewer and sent:false verified.
- OpenAPI refreshed from native-acceptance-backend-api-1. Normalized examples contain synthetic records only, no credentials. Frontend source mounted read-only from C:/Users/pkart/orca/workspaces/marketing-system/redesign-frontend. Its own mock tests are separate from these real-stack checks.
- Direct localhost8094 remains refused with mirrored WSL; optional loopback gateway health8095 returned200. No deployed environments, provider spend or outbound messages touched.

Final rebuild runtime smoke passed for manual and native routes with actual restricted roles and no provider calls. CI-style OpenAPI comparison against the running rebuilt API passed. Document links and response-example secret-field checks passed. Exported examples validate against their public response models. A targeted seven-test frontend-support rerun verifies the final resume scheduling restoration.

## Authorized real DEV discovery — 11 October 2026

User explicitly requested real discovery against the DEV dashboard. Actual deployed dashboard forms/API/n8n/Brave/xKiro ran through an SSH loopback forward after public HTTP returned403 and no GUI browser was available. Original zero-lead results were traced to strict name/quote mismatches, incomplete HTML entity decoding and zeroed usage counters. Patched DEV discovery Code nodes and matching repository generator; 73 n8n JavaScript tests pass. Final job90c1b0da-3bbc-4b06-bf3c-fb509bb03796 accepted Soon Lee Transport Sdn Bhd; rendered Leads/detail and Discovered Leads → All verified, research queued automatically. Execution retention restored to none. No sending, app deployment or native cutover. See ../dev-discovery-acceptance.md for evidence and public-ingress limitations.

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
