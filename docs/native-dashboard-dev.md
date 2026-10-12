# Native DEV dashboard and provider setup

The native DEV dashboard now uses the existing `dashboard-dev.obsidian.cam` route on loopback port 8081 and talks to the native FastAPI API over the private Compose network. The legacy dashboard remains available on loopback port 8082 for rollback. Legacy and native data stores stay separate; accounts and catalog entries must be provisioned in the native workspace.

## Runtime services

The deployment Compose environment must load both `docker-compose.yml` and `compose.backend.yml` (the DEV server already does this because `docker compose run backend-migrate` resolves the service). The regular deployment helper continues to build and start `dashboard-dev`; that service now depends on the native API and worker and uses `dashboard/Dockerfile.native`. Its root path redirects to `/dashboard` so the existing deployment health checks remain valid. The native dashboard binds to the existing route at `127.0.0.1:8081`; the legacy dashboard moves to `127.0.0.1:8082`. The binding is fixed so any old `NATIVE_DASHBOARD_HOST_PORT=8093` setting is ignored. Do not expose container ports directly to the public network.

The former dashboard is `dashboard-legacy-dev`, bound to `127.0.0.1:8082`. It still connects to the legacy API and database. Start it for rollback with `docker compose up -d dashboard-legacy-dev`; it does not share native accounts or product data.

## Restore the native LorrySystem catalog

After native migrations and the first native admin/workspace bootstrap have completed, run this idempotent command from `/opt/lorrysystem/dev/lorrysystem-dev`:

```bash
docker compose run --rm --no-deps backend-migrate \
  python -m marketing_backend.catalog_seed \
  --workspace LorrySystem --confirm-workspace LorrySystem
```

It adds the nine solution lines and seven proposed ICP segments from [the reviewed catalog reference](lorrysystem-catalog-reference.md) only when their stable catalog code is absent. It preserves the existing `AI_DASHCAM`, `GPS`, `MDVR` and `TMS` codes and never overwrites existing entries. The ICP profiles are proposed customer segments; administrators should review them before activating discovery. Plant/weighbridge, waste-management and custom-integration entries are explicitly marked custom scope, not standard deployment-ready products. Fuel sensors, TPMS and alcohol detectors are not included because current availability needs confirmation.

Open `https://dashboard-dev.obsidian.cam`, sign in with the native admin account created through `backend-migrate`, and use **Product setup** to enter the product overview, Malaysian target customers, English message language and campaign preferences. The catalog restore populates actual offers and proposed ICP profiles. Product activation is explicit and queues setup work; discovery candidates still require human acceptance.

## Configure Brave and xKiro on the DEV host

Provider keys belong in the ignored server `/opt/lorrysystem/dev/lorrysystem-dev/.env`, never in Git or the browser dashboard. Edit the existing file privately (`nano /opt/lorrysystem/dev/lorrysystem-dev/.env`), preserve its three database passwords, and set the following provider values:

```dotenv
BACKEND_BRAVE_SEARCH_API_KEY=<Brave Search API key>
BACKEND_MODEL_API_KEY=<xKiro API key>
BACKEND_MODEL_BASE_URL=https://api.xkiro.com/v1
BACKEND_MODEL_NAME=mistralai/mistral-large-2512
BACKEND_MODEL_AUTH_HEADER=Authorization
BACKEND_MODEL_INPUT_USD_PER_MILLION=<verified current input rate>
BACKEND_MODEL_OUTPUT_USD_PER_MILLION=<verified current output rate>
BACKEND_SEARCH_USD_PER_REQUEST=<verified current Brave rate>
BACKEND_PROVIDER_MONTHLY_BUDGET_USD=50
```

xKiro documents the OpenAI-compatible `POST /v1/chat/completions` endpoint and accepts either `Authorization: Bearer <key>` or `x-api-key: <key>`. This adapter accepts those two header modes; set `BACKEND_MODEL_AUTH_HEADER=x-api-key` only when using that mode. See [xKiro chat completions](https://docs.xkiro.com/api/chat-completions/) and [xKiro API overview](https://docs.xkiro.com/api/overview/).

Do not guess provider rates. The worker refuses paid requests until all three rates are supplied so usage reservations have a defensible estimate. The monthly budget is a reservation cap for this backend, not a provider invoice or account-wide spending limit.

Restart the worker after saving the server environment:

```bash
docker compose up -d --force-recreate backend-worker
docker compose ps dashboard-dev backend-api backend-worker
docker compose logs --tail=100 backend-worker
```

The idle worker can have no log output. Confirm that the API key variables are present without printing their values:

```bash
docker compose exec backend-worker python -c 'import os; print("Brave key:", bool(os.getenv("BRAVE_SEARCH_API_KEY"))); print("xKiro key:", bool(os.getenv("MODEL_API_KEY"))); print("Rates:", all(os.getenv(k) for k in ("SEARCH_USD_PER_REQUEST", "MODEL_INPUT_USD_PER_MILLION", "MODEL_OUTPUT_USD_PER_MILLION")))'
```

The native dashboard BFF currently stores sessions in process memory and is intentionally run as one container process for DEV. A multi-process or production cutover requires shared session storage and a reviewed account/data migration.
