# Native DEV parallel rollout

The native Python API, durable worker and native dashboard can run alongside the existing DEV application for cutover validation. The legacy dashboard/API, PostgreSQL data, n8n instances and production services remain in place during this phase. This is a parallel DEV stack, not a production-ready migration.

## Runtime

The root `docker-compose.yml` includes `compose.backend.yml`. Docker documents this feature as requiring Compose v2.20.3 or newer ([Compose include documentation](https://docs.docker.com/compose/how-tos/multiple-compose-files/include/)). A normal DEV Compose deployment therefore defines both the legacy services and these native services:

| Native service | Purpose | Host binding |
| --- | --- | --- |
| `backend-db` | Separate PostgreSQL database and persistent volume | Internal Compose network only |
| `backend-migrate` | Runs native schema migrations before API/worker startup | No host port |
| `backend-api` | Workspace-scoped native API | `127.0.0.1:8020` by default (`NATIVE_API_HOST_PORT` can override it) |
| `backend-worker` | Native setup, discovery and lead-preparation execution | No host port |
| `dashboard-dev` | Native dashboard/BFF, single process in DEV | `127.0.0.1:8081` |

The native database is intentionally separate from the legacy PostgreSQL database. No legacy users, workspaces, catalogs, leads, approvals or provider credentials are copied by starting this stack. The named native database volume must be retained across deployments and backed up separately.

## DEV environment values

Add these variables to the server's ignored, root-owned `/opt/lorrysystem/dev/lorrysystem-dev/.env`. Do not commit the server `.env` or paste its values into a ticket/chat. Keep the file owned by `root:root` with mode `600`, as required by the DEV deploy helper.

- `BACKEND_DB_PASSWORD`, `BACKEND_API_DB_PASSWORD` and `BACKEND_WORKER_DB_PASSWORD`: three different URL-safe hex passwords (for example, generated with `openssl rand -hex 32`).
- `BACKEND_MODEL_API_KEY` and `BACKEND_BRAVE_SEARCH_API_KEY`: shared native worker credentials. The xKiro model base URL/name/auth header already have defaults in `.env.example`.
- `BACKEND_MODEL_INPUT_USD_PER_MILLION`, `BACKEND_MODEL_OUTPUT_USD_PER_MILLION` and `BACKEND_SEARCH_USD_PER_REQUEST`: confirmed provider rates. The worker fails closed before paid calls when credentials or rates are absent. `BACKEND_PROVIDER_MONTHLY_BUDGET_USD` defaults to `50` for API-provider reservations only.
- `NATIVE_DASHBOARD_SECURE_COOKIES=true` when opened through HTTPS. Set it to `false` only for local plain-HTTP testing.

Do not reuse the legacy database password for the native database roles. Do not put provider keys into a frontend container or browser.

## First startup and administrator bootstrap

The DietPi helper at `/usr/local/sbin/lorry-dev-deploy` was updated on 14 October 2026. It now starts and waits for both PostgreSQL databases, makes separate protected backups before migrations, builds `marketing-api-dev`, `backend-api`, `backend-worker` and `dashboard-dev`, runs both Alembic migrations, and starts the native API, worker and dashboard. It verifies that the worker container remains running, retries native API and dashboard HTTP 200 health checks, checks both migration revisions, and includes native service logs when health checks fail. Feature-branch deploys are blocked from changing the native Compose and Docker build files.

The helper retains ten pairs of legacy/native database backups. Its read-only preflight can be run with:

```bash
sudo /usr/local/sbin/lorry-dev-deploy check develop
```

All three native DB passwords and the provider configuration still need to be present in the protected server `.env` before deployment. The native dashboard remains loopback-only on port 8081; configure its HTTPS route separately. The old n8n and legacy services remain available during this stage.

To verify the native services without stopping legacy or n8n services:

```bash
cd /opt/lorrysystem/dev/lorrysystem-dev
docker compose ps backend-db backend-migrate backend-api backend-worker dashboard-dev
curl -fsS http://127.0.0.1:8020/health
curl -fsS http://127.0.0.1:8081/health
```

For the first empty native database, bootstrap one platform administrator and the initial LorrySystem workspace interactively. The CLI prompts for the password; it is not passed in shell history:

```bash
docker compose run --rm backend-migrate \
  python -m marketing_backend.cli bootstrap \
  --email ADMIN_EMAIL --workspace LorrySystem
```

Then open the native dashboard through an authenticated HTTPS development route, or a private loopback tunnel to port `8081`. The port is not bound publicly. If the route is not configured yet, keep the legacy `dashboard-dev.obsidian.cam` route on the legacy dashboard and configure a separate DEV hostname before inviting workers to the native dashboard.

Enter the product catalog and ICP through the native setup form. Existing product data and team memberships are not imported automatically. Use synthetic company data first. Live discovery requires the shared provider keys and confirmed rates above; it uses the configured API-provider budget. Candidates remain in the review inbox until a worker explicitly accepts them.

## Release gates

This rollout is not a green light to remove n8n. Before switching DEV traffic, confirm:

1. Native migrations, API, worker and dashboard remain healthy after a restart and deployment.
2. A platform administrator can sign in, create a workspace, enter a catalog and configure the product.
3. A bounded discovery run creates sourced candidates, and only explicit human acceptance creates official leads and queues preparation.
4. Research, contact review, scoring, matching and drafts reach the intended human-approval state without sending anything.
5. A fresh dashboard route, authentication cookie policy, backups, cost reservations and rollback have been reviewed.

The dashboard session cache is process-local and the deployment uses one instance. Do not scale it horizontally or call this the final scalable cutover until shared session storage is implemented and verified. Account, workspace, catalog, lead, approval and encrypted provider-connection migration are separate work. Keep legacy DEV and production/n8n services available until the replacement passes these gates and a deliberate data cutover is complete.

## CI coverage

The application CI validates the composed configuration and builds both native and legacy images. It starts the native API, worker and dashboard beside the legacy test services and checks the native health endpoints. The separate backend PostgreSQL CI remains responsible for database-role, durable-job and worker-pipeline integration checks. CI does not deploy or modify the DietPi helper.
