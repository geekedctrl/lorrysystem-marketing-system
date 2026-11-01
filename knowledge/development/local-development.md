# Local development and verification

Updated: 6 October 2026. Use a disposable workspace test environment for database-mutating regression scripts.

The repository's [compose.workspace-test.yml](../../compose.workspace-test.yml) runs PostgreSQL, API and dashboard with a dedicated test volume. API: `http://127.0.0.1:8011`; dashboard: `http://127.0.0.1:8091`. It does not mount the application's existing `data/` directory.

Supply `WORKSPACE_TEST_DB_PASSWORD`, `WORKSPACE_TEST_API_KEY` and `WORKSPACE_TEST_SESSION_SECRET` with independently generated values in the ignored `.env.workspace-test` file. These are disposable test secrets, not n8n provider credentials.

```powershell
docker compose --env-file .env.workspace-test -f compose.workspace-test.yml up --build -d
node --test integrations/n8n/workspace-runtime.test.js integrations/n8n/discovery.test.js integrations/n8n/research.test.js integrations/n8n/people.test.js
python dashboard/scripts/validate_research_presentation.py
```

Wait for API/dashboard readiness before running the research integration suite:

```powershell
docker exec marketing-system-workspace-test-api-1 python scripts/validate_workspace_research.py
```

The regression suite requires `APP_ENV=ci` or `workspace-test`. It creates isolated fixture workspaces, companies and users. Never point it at shared DEV or production customer data. CI's [workflow](../../.github/workflows/ci.yml) defines the complete required checks and container setup.

For first-administrator bootstrap and migration instructions, use [the workspace deployment guide](../../docs/PRODUCT_WORKSPACES.md). Preserve user-owned uncommitted changes when preparing a feature branch. Read [the repository map](repository-map.md) to locate the relevant code.
