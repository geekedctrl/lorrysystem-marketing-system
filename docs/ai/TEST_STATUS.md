# Test status — 10 October 2026 MYT

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

