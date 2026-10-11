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
