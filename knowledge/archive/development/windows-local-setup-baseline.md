> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

# LorrySystem Local Development Setup

This guide documents the commands used to bring up the LorrySystem development environment locally on Windows using Docker Desktop and PowerShell.

The local environment is isolated from shared DEV and PROD.

## 1. Architecture

Current local setup:

```text
Browser
  ↓
Local Dashboard
  ↓
Local Marketing API
  ↓
Local PostgreSQL
```

Planned full local setup:

```text
Local Dashboard ──────┐
                      ↓
                 Local API
                      ↓
               Local PostgreSQL
                      ↑
                      │
                 Local n8n
```

Each developer should use their own local secrets, local database, and local n8n runtime.

## 2. Prerequisites

Install Git, Docker Desktop, and VS Code.

Verify Docker:

```powershell
docker --version
docker compose version
docker info --format '{{.ServerVersion}}'
```

## 3. Clone the Repository

```powershell
git clone https://github.com/geekedctrl/lorrysystem-marketing-system.git
cd lorrysystem-marketing-system
git switch develop
git pull origin develop
code .
```

## 4. Create Local Environment Files

```powershell
Copy-Item .env.example .env
Copy-Item dashboard\.env.example dashboard\.env
```

These `.env` files are local only and ignored by Git.

## 5. Generate Local Secrets

```powershell
$pgPassword = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
$apiKey = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
$dashboardSecret = ([guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N"))
```

Update root `.env`:

```powershell
$content = Get-Content .env

$content = $content `
    -replace '^POSTGRES_PASSWORD=.*$', "POSTGRES_PASSWORD=$pgPassword" `
    -replace '^MARKETING_API_KEY=.*$', "MARKETING_API_KEY=$apiKey"

$content | Set-Content .env
```

Update `dashboard\.env`:

```powershell
$content = Get-Content dashboard\.env

$content = $content `
    -replace '^MARKETING_API_KEY=.*$', "MARKETING_API_KEY=$apiKey" `
    -replace '^DASHBOARD_SESSION_SECRET=.*$', "DASHBOARD_SESSION_SECRET=$dashboardSecret"

$content | Set-Content dashboard\.env
```

Remove temporary variables:

```powershell
Remove-Variable pgPassword,apiKey,dashboardSecret
```

Do not commit or share the generated `.env` files.

## 6. Validate Docker Compose

```powershell
docker compose config -q
Write-Host "COMPOSE VALID"
```

## 7. Start PostgreSQL and API

```powershell
docker compose up -d --build postgres-dev marketing-api-dev
docker compose ps
```

Expected:

```text
lorrysystem-dev-postgres
lorrysystem-dev-marketing-api
```

## 8. Apply Database Migrations

```powershell
docker exec lorrysystem-dev-marketing-api alembic upgrade head
docker exec lorrysystem-dev-marketing-api alembic current
```

Expected:

```text
008 (head)
```

## 9. Test Local API

```powershell
curl.exe http://127.0.0.1:8001/health
```

Expected:

```json
{"status":"ok","service":"lorrysystem-marketing-api"}
```

Optional OpenAPI test:

```powershell
curl.exe http://127.0.0.1:8001/openapi.json -o openapi-test.json
Get-Item openapi-test.json
Remove-Item openapi-test.json
```

## 10. Retrieve Local ICP IDs

```powershell
docker exec lorrysystem-dev-postgres `
  psql -U lorrysystem_dev -d lorrysystem_dev `
  -c "SELECT id, code FROM icp_profiles ORDER BY code;"
```

You should get IDs for:

```text
COMMERCIAL_ENTERPRISE
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
```

Optional table inspection:

```powershell
docker exec lorrysystem-dev-postgres `
  psql -U lorrysystem_dev -d lorrysystem_dev `
  -c "\d icp_profiles"
```

## 11. Configure Dashboard ICP IDs

Edit:

```text
dashboard\.env
```

Set:

```env
ICP_LOGISTICS_HAULAGE_ID=LOCAL_UUID
ICP_PASSENGER_TRANSPORT_ID=LOCAL_UUID
ICP_COMMERCIAL_ENTERPRISE_ID=LOCAL_UUID
```

Also ensure:

```env
MARKETING_API_BASE_URL=http://lorrysystem-dev-marketing-api:8000
DASHBOARD_REVIEWER_IDENTITY=dev-reviewer
TRUST_CLOUDFLARE_IDENTITY=false
```

## 12. Start Dashboard

```powershell
docker compose up -d --build dashboard-dev
docker compose ps
```

Expected local containers:

```text
lorrysystem-dev-postgres
lorrysystem-dev-marketing-api
lorrysystem-dev-dashboard
```

## 13. Test Dashboard

```powershell
curl.exe -sS -D - -o NUL http://127.0.0.1:8081/
```

Expected:

```text
HTTP/1.1 302 Found
location: /dashboard
```

Open:

```text
http://127.0.0.1:8081/dashboard
```

## 14. Test Dashboard → API

```powershell
docker exec lorrysystem-dev-dashboard `
  python -c "import httpx; r=httpx.get('http://lorrysystem-dev-marketing-api:8000/health'); print(r.status_code, r.text)"
```

Expected:

```text
200 {"status":"ok","service":"lorrysystem-marketing-api"}
```

## 15. Local n8n

Yes: to test the complete orchestration locally, each developer should also run a separate local n8n container.

That local n8n should:

- use its own persistent local data
- use its own encryption key
- use local-only credentials
- call the local Marketing API
- never reuse DEV or PROD credentials
- never connect directly to PostgreSQL
- communicate with PostgreSQL only through the Marketing API

Target:

```text
Local n8n
   ↓
Local Marketing API
   ↓
Local PostgreSQL
```

Important: the current Git repository does not yet contain the local n8n runtime/workflow setup. We still need to add a safe local n8n configuration and sanitized workflow exports before interns can reproduce the full orchestration locally.

Never copy these into a developer machine:

```text
DEV .n8n runtime data
PROD .n8n runtime data
DEV credentials
PROD credentials
DEV encryption keys
PROD encryption keys
```

## 16. Local vs DEV vs PROD

```text
LOCAL
.env
dashboard/.env
local PostgreSQL data
local n8n data

DEV SERVER
.env
dashboard/.env
DEV PostgreSQL data
DEV n8n data

PROD SERVER
.env
dashboard/.env
PROD PostgreSQL data
PROD n8n data
```

Git contains code and safe templates, not real environment files.

## 17. What Happens When Code Is Pushed

A developer's local `.env` is ignored by Git.

Example:

```text
Intern laptop:
MARKETING_API_KEY=LOCAL_KEY

GitHub:
No .env file

DEV server:
MARKETING_API_KEY=DEV_KEY
```

When the DEV server pulls new code, it continues using its existing DEV `.env`.

## 18. Useful Local Commands

Status:

```powershell
docker compose ps
```

API health:

```powershell
curl.exe http://127.0.0.1:8001/health
```

Dashboard:

```text
http://127.0.0.1:8081/dashboard
```

Logs:

```powershell
docker logs --tail 100 lorrysystem-dev-marketing-api
docker logs --tail 100 lorrysystem-dev-dashboard
docker logs --tail 100 lorrysystem-dev-postgres
```

Migration status:

```powershell
docker exec lorrysystem-dev-marketing-api alembic current
```

Apply migrations:

```powershell
docker exec lorrysystem-dev-marketing-api alembic upgrade head
```

## 19. Stop Local Environment

```powershell
docker compose down
```

Bring it back:

```powershell
docker compose up -d --build
```

## 20. Development Flow

```text
git switch develop
        ↓
git pull
        ↓
create feature branch
        ↓
code
        ↓
run local stack
        ↓
test API / Dashboard / Database
        ↓
test local n8n once configured
        ↓
commit
        ↓
push feature branch
        ↓
shared DEV integration testing
```

Local testing verifies a feature in isolation.

Shared DEV verifies it against the real LorrySystem integration environment, including DEV n8n.
