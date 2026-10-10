# LorrySystem Marketing & Lead Generation

Internal marketing, lead-generation, research, scoring, product-matching, approval, and outreach platform for LorrySystem.

This repository contains the core application used by the **development environment** and is the source of truth for application code changes before they are promoted to production.

> **Important:** Never commit passwords, API keys, database files, `.env` files, n8n credentials, or other runtime secrets to this repository.

---

## Product workspaces update

Administrators can now set up a product and its catalog through application forms,
then run shared automation through an outreach draft awaiting human approval.
See [Product onboarding and shared automation](docs/product-onboarding.md) for
the one-time platform connection, access boundaries, automatic preparation rules,
pause/retry controls and release steps. Sending remains a separate stage.

The application now supports private product workspaces with email/password
accounts, workspace roles, catalogs and automation credentials. Existing data
migrates into the LorrySystem workspace. The API applies Alembic migrations before
serving requests, and the dashboard requires sign-in.

Read [Product workspace deployment and access guide](docs/PRODUCT_WORKSPACES.md)
for first-administrator setup, migration/backup requirements and the n8n transition.
The [n8n workspace adaptation package](integrations/n8n/README.md) includes an
importable preflight and tools for binding exported automation to each workspace.
This update supersedes the single-workspace authentication and ICP environment
configuration described in older sections below.

## 1. Project Overview

The system is built around four main components:

- **FastAPI** — REST API and application/business logic
- **PostgreSQL** — persistent application database
- **Dashboard** — server-rendered FastAPI/Jinja web interface
- **n8n** — workflow orchestration and automation

Typical lead lifecycle:

```text
Lead Candidate
      ↓
Accepted as Lead
      ↓
Research
      ↓
Scoring / Qualification
      ↓
Product Matching
      ↓
Marketing Action Draft
      ↓
Approval
      ↓
Approved Outreach Action
```

Research automation is designed to collect publicly available company information and relevant company contacts, including employees/executives and public LinkedIn or other social profiles when available.

---

## 2. Architecture

```text
                         ┌──────────────────────┐
                         │      Dashboard       │
                         │   FastAPI + Jinja    │
                         └──────────┬───────────┘
                                    │ REST API
                                    ▼
┌─────────────┐            ┌──────────────────────┐
│     n8n     │───────────▶│   Marketing API      │
│ Automation  │ REST API   │       FastAPI        │
└─────────────┘            └──────────┬───────────┘
                                      │ SQLAlchemy
                                      ▼
                           ┌──────────────────────┐
                           │     PostgreSQL       │
                           └──────────────────────┘
```

### Security boundary

Only the Marketing API is allowed to communicate directly with PostgreSQL.

```text
n8n        ✕ PostgreSQL
Dashboard  ✕ PostgreSQL
Internet   ✕ PostgreSQL

Marketing API ✓ PostgreSQL
```

The Dashboard and n8n must communicate with the database **through the API only**.

---

## 3. Repository Structure

```text
lorrysystem-marketing-system/
├── api/
│   ├── app/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── routers/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── main.py
│   │   └── security.py
│   ├── scripts/
│   ├── alembic/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── alembic.ini
│
├── dashboard/
│   ├── app/
│   │   ├── static/
│   │   ├── templates/
│   │   ├── api_client.py
│   │   ├── config.py
│   │   └── main.py
│   ├── scripts/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── .env.example
│
├── database/
│   └── migrations/
│       └── versions/
│
├── docker-compose.yml
├── .env.example
├── .gitignore
└── README.md
```

### n8n

n8n is intentionally maintained outside this Git repository because its runtime data, credentials, encryption keys, and workflow state must not be committed.

Development n8n:

```text
/opt/lorrysystem/dev/n8n-dev
```

Production n8n:

```text
/opt/lorrysystem/prod/n8n
```

Exported workflows may be version-controlled later, but credentials and runtime state must never be committed.

---

## 4. Environments

### Development

Application:

```text
/opt/lorrysystem/dev/lorrysystem-dev
```

n8n:

```text
/opt/lorrysystem/dev/n8n-dev
```

Public services:

```text
https://dashboard-dev.obsidian.cam
https://n8n-dev.obsidian.cam
```

DEV host ports:

```text
Dashboard: 127.0.0.1:8081
API:       127.0.0.1:8001
n8n:       127.0.0.1:5679
```

### Production

Application:

```text
/opt/lorrysystem/prod/lorrysystem-marketing
```

Dashboard:

```text
/opt/lorrysystem/prod/lorrysystem-dashboard
```

n8n:

```text
/opt/lorrysystem/prod/n8n
```

Public services:

```text
https://dashboard.obsidian.cam
https://n8n.obsidian.cam
```

---

## 5. DEV and PROD Isolation

DEV and PROD use separate Docker networks and separate PostgreSQL databases.

Development containers must never be attached to production Docker networks.

```text
DEV Dashboard
     ↓
DEV API
     ↓
DEV PostgreSQL

DEV n8n
     ↓
DEV API
```

and separately:

```text
PROD Dashboard
     ↓
PROD API
     ↓
PROD PostgreSQL

PROD n8n
     ↓
PROD API
```

A DEV service must never communicate directly with a PROD service.

---

## 6. API Overview

The current FastAPI OpenAPI specification contains:

| Method | Endpoints |
|---|---:|
| GET | 34 |
| POST | 23 |
| PATCH | 13 |
| DELETE | 2 |
| **Total** | **72** |

> Update this count whenever routes are added or removed.

### API router groups

- Approvals
- Candidates
- Companies
- Contacts
- Health
- Leads
- Marketing Actions
- Product Matching
- Public Fetch
- Research
- Scoring
- Workspaces and accounts

### Authentication

Protected API endpoints use:

```http
X-API-Key: <MARKETING_API_KEY>
```

The API key must come from environment configuration and must never be hard-coded or committed.

The following are intentionally unprotected:

```text
/health
/openapi.json
```

---

## 7. Lead Lifecycle

```text
Candidate
   ↓
Lead
   ↓
Research
   ↓
Lead Score
   ↓
Product Match
   ↓
Marketing Action
   ↓
Approval Request
   ↓
Approved / Rejected
```

Research may automatically start when a Candidate is accepted and becomes a Lead.

Research workers are expected to gather information such as:

- Company profile and business activity
- Official website
- Public business information
- Relevant executives
- Relevant employees
- LinkedIn profiles
- Other public social profiles
- Public evidence/source URLs

---

## 8. Database Migrations

Database schema changes are managed using **Alembic**.

Current migration head:

```text
009
```

Current migration chain:

```text
001
 ↓
002
 ↓
003
 ↓
d62d40479f83
 ↓
005
 ↓
006
 ↓
007
 ↓
008
 ↓
009
```

Never edit an already-applied migration simply to change production behavior. Create a new migration instead.

Check migration status:

```bash
docker exec lorrysystem-dev-marketing-api alembic current
docker exec lorrysystem-dev-marketing-api alembic heads
```

Apply migrations in DEV:

```bash
docker exec lorrysystem-dev-marketing-api alembic upgrade head
```

Database migrations must be tested in DEV before being promoted to production.

---

## 9. Git Branching Strategy

```text
main
  ↑
develop
  ↑
feature/*
```

### `main`

Stable, reviewed, production-ready code.

### `develop`

Integration branch for development and testing.

### `feature/*`

All new work should start from `develop`.

Examples:

```text
feature/research-worker
feature/company-contact-discovery
feature/dashboard-filters
feature/product-matching
fix/research-validation
```

---

## 10. Intern Development Workflow

The intern should **not edit the live DEV directory directly over SSH**.

Development should happen on the intern's own computer.

Clone:

```bash
git clone https://github.com/geekedctrl/lorrysystem-marketing-system.git
cd lorrysystem-marketing-system
```

Start from `develop`:

```bash
git switch develop
git pull origin develop
```

Create a feature branch:

```bash
git switch -c feature/<task-name>
```

Example:

```bash
git switch -c feature/research-worker-improvements
```

Commit:

```bash
git status
git add .
git commit -m "feat: improve research worker"
```

Push:

```bash
git push -u origin feature/research-worker-improvements
```

Then create a Pull Request:

```text
feature/<task>
        ↓
     develop
```

The feature should be reviewed and tested before merge.

---

## 11. Deploying Changes to DEV

After a Pull Request is merged into `develop`:

```bash
cd /opt/lorrysystem/dev/lorrysystem-dev

git switch develop
git pull --ff-only origin develop
```

Rebuild/restart:

```bash
docker compose up -d --build
```

If there is a new migration:

```bash
docker exec lorrysystem-dev-marketing-api alembic upgrade head
```

Verify:

```bash
docker ps
curl http://127.0.0.1:8001/health
```

Public DEV services:

```text
https://dashboard-dev.obsidian.cam
https://n8n-dev.obsidian.cam
```

---

## 12. Promoting to Production

Production should only receive code that has already been:

1. Developed in a feature branch
2. Reviewed
3. Merged into `develop`
4. Deployed to DEV
5. Tested successfully in DEV
6. Approved for release

Flow:

```text
feature/*
   ↓
develop
   ↓
DEV testing
   ↓
main
   ↓
PROD deployment
```

Do not make experimental changes directly on production.

---

## 13. Environment Configuration

Real configuration is stored in `.env` files and is intentionally excluded from Git.

Templates:

```text
.env.example
dashboard/.env.example
```

Typical API/database configuration:

```env
APP_ENV=development

POSTGRES_HOST=postgres-dev
POSTGRES_PORT=5432
POSTGRES_DB=lorrysystem_dev
POSTGRES_USER=lorrysystem_dev
POSTGRES_PASSWORD=CHANGE_ME

MARKETING_API_KEY=CHANGE_ME
```

Dashboard configuration:

```env
MARKETING_API_BASE_URL=http://lorrysystem-dev-marketing-api:8000
MARKETING_API_KEY=CHANGE_ME

DASHBOARD_SESSION_SECRET=CHANGE_ME
DASHBOARD_REVIEWER_IDENTITY=dev-reviewer
TRUST_CLOUDFLARE_IDENTITY=false

ICP_LOGISTICS_HAULAGE_ID=CHANGE_ME
ICP_PASSENGER_TRANSPORT_ID=CHANGE_ME
ICP_COMMERCIAL_ENTERPRISE_ID=CHANGE_ME
```

Never put real secrets into `.env.example`.

---

## 14. Files That Must Never Be Committed

Do not commit:

```text
.env
.env.*
data/
secrets/
.n8n/
PostgreSQL database files
database dumps containing real data
private keys
certificates
credentials
runtime logs
backup files
```

Before committing:

```bash
git status
git diff --cached
```

---

## 15. Useful DEV Commands

Application status:

```bash
cd /opt/lorrysystem/dev/lorrysystem-dev
docker compose ps
```

API logs:

```bash
docker logs --tail 100 lorrysystem-dev-marketing-api
```

Dashboard logs:

```bash
docker logs --tail 100 lorrysystem-dev-dashboard
```

PostgreSQL logs:

```bash
docker logs --tail 100 lorrysystem-dev-postgres
```

n8n logs:

```bash
docker logs --tail 100 n8n-dev
```

DEV API health:

```bash
curl http://127.0.0.1:8001/health
```

DEV dashboard response:

```bash
curl -sS -D - -o /dev/null http://127.0.0.1:8081/
```

DEV n8n health:

```bash
curl http://127.0.0.1:5679/healthz
```

---

## 16. Development Rules

1. Never work directly on `main`.
2. Start new work from `develop`.
3. Use a dedicated `feature/*` or `fix/*` branch.
4. Never commit secrets.
5. Never connect n8n directly to PostgreSQL.
6. Never connect the Dashboard directly to PostgreSQL.
7. Do not connect DEV containers to PROD networks.
8. Test database migrations in DEV first.
9. Use the API as the application boundary.
10. Submit changes through Pull Requests.
11. Keep commits focused and descriptive.
12. Do not edit production code directly on the server.

---

## 17. Technology Stack

- Python
- FastAPI
- SQLAlchemy
- PostgreSQL 17
- Alembic
- Jinja2
- HTTPX
- Docker
- Docker Compose
- n8n
- Cloudflare Tunnel
- Git / GitHub

---

## 18. Current Status

The isolated DEV environment currently includes:

- DEV PostgreSQL
- DEV Marketing API
- DEV Dashboard
- DEV n8n
- Separate DEV Docker networks
- API authentication
- Database migrations through revision `009`
- Public DEV Dashboard
- Public DEV n8n
- Git `main` and `develop` workflow
- Feature branch development workflow
- End-to-end functional lifecycle testing

The DEV environment has been validated through the complete application lifecycle from candidate creation through approval.

---

## 19. Repository

GitHub:

```text
https://github.com/geekedctrl/lorrysystem-marketing-system
```

Primary branches:

```text
main
develop
```

All active development should be performed through feature branches created from `develop`.

## Campaign Strategist

Mock-first campaign proposals, evidence, channel suggestions and human strategy review are documented in [Campaign Strategist](docs/campaign-strategist.md). Live creative generation and external delivery remain separate milestones. Engineering continuity starts at [AI handoff](docs/ai/HANDOFF.md).
