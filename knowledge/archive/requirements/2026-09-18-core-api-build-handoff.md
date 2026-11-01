> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Marketing API — HANDOFF

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**Environment:** Self-hosted DietPi / Ubuntu-style Linux server with Docker Compose  
**Current date:** 18 September 2026  
**Status:** Core database + Companies + Contacts + Leads + Research API complete and validated; Scoring API is next.

---

# 1. Purpose of This Handoff

This file is the authoritative continuation point for the LorrySystem Marketing API build.

A new chat/session should **continue from the current state** and should **not rebuild completed components unless a verified issue requires it**.

The immediate next stage is:

```text
Scoring API
    ↓
Product Matching
    ↓
Marketing Actions
    ↓
Approval API
```

---

# 2. Architecture Rules — MUST PRESERVE

The architecture is:

```text
n8n
  │
  │ HTTP / JSON
  ▼
Marketing API
  │
  │ SQLAlchemy / psycopg
  ▼
PostgreSQL
```

Never change this into:

```text
n8n ─────► PostgreSQL
```

Rules:

```text
n8n       ✕ PostgreSQL
Dashboard ✕ PostgreSQL
Internet  ✕ PostgreSQL

Marketing API ✓ PostgreSQL
```

Responsibilities:

```text
Marketing API
├── validation
├── duplicate detection
├── lifecycle transitions
├── scoring logic
├── product matching
├── approval logic
├── event logging
└── database access

PostgreSQL
└── persistent storage + hard integrity constraints

n8n
└── automation / orchestration only
```

Do **not** integrate n8n yet. Finish the API business layer first so n8n workflows do not need to be rewritten every time the API contract changes.

---

# 3. Project Root

Current project path:

```text
/opt/lorrysystem-marketing
```

Current structure:

```text
/opt/lorrysystem-marketing/
├── docker-compose.yml
├── .env
├── .env.example
├── .gitignore
│
├── data/
│   └── postgres/
│
├── database/
│   └── migrations/
│       └── versions/
│
├── api/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   │
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   └── config.py
│   │   │
│   │   ├── db/
│   │   │   ├── __init__.py
│   │   │   ├── base.py
│   │   │   └── session.py
│   │   │
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   ├── catalog.py
│   │   │   ├── companies.py
│   │   │   ├── leads.py
│   │   │   └── marketing.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── company.py
│   │   │   ├── contact.py
│   │   │   ├── lead.py
│   │   │   └── research.py
│   │   │
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── health.py
│   │   │   ├── companies.py
│   │   │   ├── contacts.py
│   │   │   ├── leads.py
│   │   │   └── research.py
│   │   │
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── company_service.py
│   │       ├── contact_service.py
│   │       ├── lead_service.py
│   │       └── research_service.py
│   │
│   ├── scripts/
│   │   └── validate_research_api.py
│   │
│   ├── alembic/
│   ├── alembic.ini
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .dockerignore
│
├── dashboard/
├── backups/
└── docs/
```

---

# 4. Docker Containers

Current containers:

```text
lorrysystem-postgres
lorrysystem-marketing-api
n8n
n8n-cloudflared
```

PostgreSQL:

```text
Image: postgres:17-alpine
Container: lorrysystem-postgres
Database: lorrysystem_marketing
Application user: marketing_app
```

Marketing API:

```text
Container: lorrysystem-marketing-api
Internal port: 8000
Framework: FastAPI
```

Important:

```text
PostgreSQL port 5432 is NOT published to the host.
```

Seeing this in `docker ps` is acceptable:

```text
5432/tcp
```

It must **not** look like:

```text
0.0.0.0:5432->5432/tcp
```

---

# 5. Docker Networks

Database network:

```text
lorrysystem-db-net
```

Verified:

```text
Internal=true
```

Current membership:

```text
lorrysystem-db-net
├── lorrysystem-postgres
└── lorrysystem-marketing-api
```

API network:

```text
lorrysystem-api-net
```

Marketing API belongs to:

```text
lorrysystem-api-net
lorrysystem-db-net
```

n8n currently belongs only to:

```text
n8n_default
```

n8n is **not** attached to `lorrysystem-db-net`.

This isolation is intentional.

---

# 6. Persistent PostgreSQL Storage

Persistent database path:

```text
/opt/lorrysystem-marketing/data/postgres
```

Docker Compose mapping:

```text
./data/postgres:/var/lib/postgresql/data
```

Persistence has been tested successfully across container restart.

---

# 7. Environment Variables

The project uses:

```text
/opt/lorrysystem-marketing/.env
```

Expected variables:

```env
POSTGRES_DB=lorrysystem_marketing
POSTGRES_USER=marketing_app
POSTGRES_PASSWORD=<secret>

POSTGRES_HOST=postgres
POSTGRES_PORT=5432

APP_ENV=development
```

Never paste the real PostgreSQL password into chat.

`.env` is ignored by Git.

---

# 8. Marketing API Stack

Current API stack:

```text
Python
FastAPI
Uvicorn
SQLAlchemy 2.x
Alembic
Psycopg 3
Pydantic Settings
```

Connection flow:

```text
FastAPI
   ↓
SQLAlchemy
   ↓
psycopg
   ↓
postgres:5432
```

The API uses Docker DNS hostname:

```text
postgres
```

not `localhost`.

---

# 9. Health Endpoints

Implemented:

```text
GET /health
GET /health/db
```

Verified DB health result:

```json
{
  "status": "ok",
  "database": "reachable"
}
```

---

# 10. Current Database Tables

The initial schema contains:

```text
products
icp_profiles
companies
contacts
leads
lead_research
research_sources
lead_scores
product_matches
marketing_actions
approval_requests
events
```

Plus:

```text
alembic_version
```

---

# 11. Alembic Status

Completed migrations:

```text
001_initial_schema
002_seed_initial_catalog
003_require_icp_and_prevent_duplicate_active_leads
d62d40479f83_research_lifecycle
```

Migration chain:

```text
001
 ↓
002
 ↓
003
 ↓
d62d40479f83
```

## Migration 001

Created the initial 12-table application schema.

## Migration 002

Seeded initial Products and ICP Profiles.

Products:

```text
TMS
GPS
AI_DASHCAM
DMS
MDVR
FUEL_MONITORING
```

ICPs:

```text
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
COMMERCIAL_ENTERPRISE
```

## Migration 003

Implemented two new MVP1 rules:

```text
1. Every lead MUST have an ICP.
2. Only one ACTIVE lead may exist per company + ICP.
```

Migration 003 changes:

```text
leads.icp_profile_id → NOT NULL
FK ON DELETE SET NULL → ON DELETE RESTRICT
partial unique active-lead index added
```

Current partial unique index:

```text
idx_leads_active_company_icp_unique
```

Verified PostgreSQL definition conceptually:

```sql
CREATE UNIQUE INDEX idx_leads_active_company_icp_unique
ON leads (company_id, icp_profile_id)
WHERE status IN (
    'DISCOVERED',
    'RESEARCHING',
    'QUALIFIED',
    'READY_FOR_OUTREACH',
    'CONTACTED',
    'REPLIED'
);
```

Terminal statuses are intentionally excluded:

```text
CONVERTED
DISQUALIFIED
LOST
```

---

# 12. New Lead Rule — IMPORTANT

This is now a hard MVP1 rule:

```text
EVERY LEAD MUST BELONG TO ONE ICP.
```

Therefore:

```text
icp_profile_id is REQUIRED.
```

This is enforced at:

```text
FastAPI / Pydantic
SQLAlchemy
PostgreSQL NOT NULL
```

The PostgreSQL FK uses:

```text
ON DELETE RESTRICT
```

because deleting an ICP that is still referenced by a lead must not silently make the lead invalid.

---

# 13. Lead Duplicate Rule — IMPORTANT

Lead uniqueness is:

```text
company_id + icp_profile_id
```

while the lead is active.

Do **not** include:

```text
primary_contact_id
```

in lead uniqueness.

Reason:

```text
ABC Logistics
├── John Tan — Fleet Manager
├── Sarah Lee — Operations Manager
└── One LOGISTICS_HAULAGE opportunity
```

The primary contact can change while the sales opportunity remains the same.

Active lead statuses:

```text
DISCOVERED
RESEARCHING
QUALIFIED
READY_FOR_OUTREACH
CONTACTED
REPLIED
```

Terminal statuses:

```text
CONVERTED
DISQUALIFIED
LOST
```

After a lead reaches a terminal state, a new future lead may be created for the same company + ICP.

---

# 14. Lead Duplicate Protection — TWO LAYERS

## API Layer

The Marketing API checks for an existing active lead with the same:

```text
company_id
+
icp_profile_id
```

Duplicate response:

```text
HTTP 409 Conflict
```

Verified response:

```json
{
  "detail": {
    "message": "An active lead already exists for this company and ICP profile.",
    "existing_lead_id": "<existing-lead-uuid>",
    "existing_status": "DISCOVERED"
  }
}
```

## PostgreSQL Layer

Migration 003 added:

```text
idx_leads_active_company_icp_unique
```

This prevents race-condition duplicates even if two requests pass the API pre-check simultaneously.

Final architecture:

```text
POST /api/leads
        │
        ▼
Marketing API duplicate check
        │
        ├── duplicate → HTTP 409
        │
        ▼
PostgreSQL partial unique index
```

---

# 15. Company API

Implemented:

```text
POST /api/companies
GET  /api/companies
GET  /api/companies/{company_id}
```

Company duplicate detection checks:

```text
1. Domain
2. Normalized company name
3. Website
```

Verified duplicate behavior:

```text
HTTP 409 Conflict
```

Database also has case-insensitive unique company-domain protection.

---

# 16. Contact API

Implemented:

```text
POST /api/contacts
GET  /api/contacts
GET  /api/contacts/{contact_id}
GET  /api/contacts?company_id=<uuid>
```

Current validation:

```text
Company must exist
Email normalized
Duplicate email checked
Contact linked to company
```

Current contact email rule for MVP1:

```text
case-insensitive globally unique email
```

Do not change this yet.

Future architecture review item:

```text
global email uniqueness
vs
company_id + email
```

This may matter later for shared mailboxes.

---

# 17. Leads API

Implemented:

```text
POST  /api/leads
GET   /api/leads
GET   /api/leads/{lead_id}
PATCH /api/leads/{lead_id}/status
```

Lead creation requires:

```text
company_id         REQUIRED
icp_profile_id     REQUIRED
primary_contact_id OPTIONAL
priority           LOW / MEDIUM / HIGH
```

New leads begin as:

```text
DISCOVERED
```

Current validation:

```text
Company exists                         ✓
Primary contact exists                 ✓
Primary contact belongs to company     ✓
ICP exists                             ✓
ICP required                           ✓
Active duplicate does not exist        ✓
```

---

# 18. Lead Lifecycle

Current lifecycle:

```text
DISCOVERED
    ↓
RESEARCHING
    ↓
QUALIFIED
    ↓
READY_FOR_OUTREACH
    ↓
CONTACTED
    ↓
REPLIED
    ↓
CONVERTED
```

Alternative exits:

```text
DISQUALIFIED
LOST
```

Current API transition implementation is conservative and sequential.

Invalid status jumps return:

```text
HTTP 409 Conflict
```

Lifecycle timestamps currently include:

```text
discovered_at
qualified_at
contacted_at
converted_at
created_at
updated_at
```

---

# 19. Lead Event Logging

Lead creation logs:

```text
lead_discovered
```

Lead lifecycle transitions also log events.

Events table contains:

```text
id
event_type
entity_type
entity_id
actor_type
actor_id
metadata
created_at
```

Business event logging belongs in the Marketing API.

---

# 20. Research API — COMPLETED

The Research API has been implemented and validated for MVP1.

Research history is preserved.

Correct structure:

```text
Lead
├── Research Run 1
├── Research Run 2
├── Research Run 3
└── ...
```

Every new research attempt creates a new:

```text
lead_research
```

row.

Previous research is never overwritten.

---

# 21. Research Statuses — IMPLEMENTED

Implemented statuses:

```text
PENDING
RUNNING
COMPLETED
PARTIAL
FAILED
```

Lifecycle:

```text
PENDING
   ↓
RUNNING
   ├──→ COMPLETED
   ├──→ PARTIAL
   └──→ FAILED
```

Invalid transitions are rejected with:

```text
HTTP 409 Conflict
```

Verified examples:

```text
PENDING → COMPLETED      ✕
PENDING → FAILED         ✕
RUNNING → RUNNING        ✕
COMPLETED → COMPLETED    ✕
COMPLETED → FAILED       ✕
```

---

# 22. Research Lifecycle Timestamps — IMPLEMENTED

`lead_research` now contains:

```text
started_at
completed_at
```

Current target fields:

```text
id
lead_id
research_status

summary
pain_points
buying_signals
company_facts

confidence
model_provider
model_name
raw_output

started_at
completed_at
researched_at
created_at
```

`researched_at` is retained temporarily as a nullable legacy compatibility field.

New research runs use:

```text
created_at     = request time
started_at     = NULL until start
completed_at   = NULL until terminal state
researched_at  = NULL until terminal completion/partial compatibility write
```

---

# 23. Research Sources — IMPLEMENTED

Multiple sources are supported per research run.

Implemented source fields:

```text
source_type
url
title
evidence
confidence
observed_at
created_at
```

Allowed source types:

```text
WEBSITE
NEWS
SOCIAL
DIRECTORY
SEARCH
OTHER
```

Research detail responses return the attached sources.

---

# 24. Research AI Metadata — IMPLEMENTED

Stored:

```text
model_provider
model_name
raw_output
confidence
```

This supports later comparison by:

```text
quality
cost
speed
confidence
qualification usefulness
```

Optional future field remains:

```text
research_trigger
```

Do not block MVP1 on this field.

---

# 25. Research API Routes — IMPLEMENTED

Implemented:

```text
POST  /api/leads/{lead_id}/research
GET   /api/leads/{lead_id}/research

GET   /api/research/{research_id}

POST  /api/research/{research_id}/sources

PATCH /api/research/{research_id}/start
PATCH /api/research/{research_id}/complete
PATCH /api/research/{research_id}/partial
PATCH /api/research/{research_id}/fail
```

Verified through:

```text
/openapi.json
```

All routes are registered in FastAPI.

---

# 26. Research Workflow — IMPLEMENTED

Verified workflow:

```text
Lead created
    ↓
DISCOVERED
    ↓
POST /api/leads/{id}/research
    ↓
Lead → RESEARCHING
Research → PENDING
    ↓
PATCH /api/research/{id}/start
    ↓
Research → RUNNING
    ↓
POST research sources
    ↓
PATCH /api/research/{id}/complete
    ↓
Research → COMPLETED
```

Failure path:

```text
PENDING → RUNNING → FAILED
```

Partial path:

```text
PENDING → RUNNING → PARTIAL
```

---

# 27. Research + Lead Lifecycle Rule — VERIFIED

When a research run is requested from a:

```text
DISCOVERED
```

lead:

```text
DISCOVERED → RESEARCHING
```

When research completes:

```text
DO NOT automatically set the lead to QUALIFIED.
```

Verified behavior:

```text
Research = COMPLETED
Lead     = RESEARCHING
```

Qualification remains a later Scoring responsibility.

Existing later active lead stages are not moved backwards when a research refresh is created.

---

# 28. Research Event Logging — IMPLEMENTED

Implemented events:

```text
research_requested
research_started
research_source_added
research_completed
research_partial
research_failed
```

Verified metadata includes examples such as:

```text
lead_id
confidence
source_count
source_id
source_type
url
failure reason
```

Lead transition event:

```text
lead_status_changed
```

is also generated when:

```text
DISCOVERED → RESEARCHING
```

---

# 29. Migration 004 — COMPLETE

Research lifecycle migration revision:

```text
d62d40479f83_research_lifecycle
```

Parent:

```text
003
```

Implemented:

```text
add started_at
add completed_at
research_status default → PENDING
researched_at → nullable
remove researched_at automatic now() default
add ck_lead_research_status
add idx_lead_research_status
```

Verified:

```text
alembic upgrade head     ✓
alembic current          ✓
alembic check            ✓
```

Current Alembic head:

```text
d62d40479f83
```

---

# 30. Research Implementation Files

Current Research implementation:

```text
api/app/models/leads.py
api/app/schemas/research.py
api/app/services/research_service.py
api/app/routers/research.py
api/app/main.py
```

Reusable validation script:

```text
api/scripts/validate_research_api.py
```

---

# 31. Research Validation — COMPLETE

Manual validation confirmed:

```text
Research cannot be created for nonexistent lead       ✓
Multiple research runs can exist for one lead         ✓
Research history is preserved                         ✓
Research history is newest first                      ✓
Sources link to correct research run                  ✓
Multiple sources are supported                        ✓
Invalid research transitions are rejected             ✓
Lead moves to RESEARCHING correctly                   ✓
Research completion does NOT auto-qualify lead        ✓
Confidence < 0 rejected                               ✓
Confidence > 100 rejected                             ✓
COMPLETED path works                                  ✓
PARTIAL path works                                    ✓
FAILED path works                                     ✓
Research events are written correctly                 ✓
```

Automated integration validation:

```text
PASS: 80
FAIL: 0
SKIP: 1
RESULT: PASSED
```

The single skip occurred because the selected automated-validation lead was already:

```text
RESEARCHING
```

so the automated test could not independently recreate:

```text
DISCOVERED → RESEARCHING
```

That transition had already been manually validated successfully.

Research API MVP1 status:

```text
COMPLETE
```


# 32. Target API Coverage Before n8n

Before connecting n8n, the Marketing API should support:

```text
/api/companies          ✓
/api/contacts           ✓
/api/leads              ✓
/api/research           ✓
/api/scoring            NEXT
/api/product-matches    TODO
/api/actions            TODO
/api/approvals          TODO
/api/events             existing event storage/logging
```

Only after these APIs stabilize should n8n integrate.

---

# 33. Current Completion Summary

```text
Infrastructure
├── PostgreSQL Docker deployment             ✓
├── Persistent PostgreSQL storage            ✓
├── Private DB network                       ✓
├── PostgreSQL not publicly exposed          ✓
├── Marketing API Docker deployment          ✓
├── API → PostgreSQL connectivity            ✓
└── n8n isolated from PostgreSQL             ✓

Database
├── SQLAlchemy models                        ✓
├── Alembic                                  ✓
├── Migration 001                            ✓
├── Migration 002                            ✓
├── Migration 003                            ✓
└── Research lifecycle migration             ✓

Companies
├── Create                                   ✓
├── List                                     ✓
├── Get by UUID                              ✓
└── Duplicate protection                     ✓

Contacts
├── Create                                   ✓
├── List                                     ✓
├── Get by UUID                              ✓
├── Company validation                       ✓
└── Email duplicate protection               ✓

Leads
├── Create                                   ✓
├── List                                     ✓
├── Get by UUID                              ✓
├── Status transition                        ✓
├── Event logging                            ✓
├── ICP mandatory                            ✓
├── API duplicate protection                 ✓
└── DB duplicate protection                  ✓

Research
├── Model changes                            ✓
├── Migration 004                            ✓
├── Schemas                                  ✓
├── Service layer                            ✓
├── Router                                   ✓
├── Sources API                              ✓
├── Lifecycle validation                     ✓
├── Event logging                            ✓
├── Historical research runs                 ✓
├── Automated validation                     ✓
└── MVP1 Research API                        COMPLETE

Next
└── Scoring API                              NEXT
```


# 34. Useful Resume Commands

Check containers:

```bash
cd /opt/lorrysystem-marketing
docker ps
```

Check API health:

```bash
docker inspect \
  --format='{{.State.Health.Status}}' \
  lorrysystem-marketing-api
```

Check PostgreSQL health:

```bash
docker inspect \
  --format='{{.State.Health.Status}}' \
  lorrysystem-postgres
```

Check Alembic:

```bash
docker exec lorrysystem-marketing-api \
alembic current
```

Expected:

```text
d62d40479f83 (head)
```

Check model/schema synchronization:

```bash
docker exec lorrysystem-marketing-api \
alembic check
```

Expected:

```text
No new upgrade operations detected.
```

Check API DB connection:

```bash
docker exec lorrysystem-marketing-api \
python -c \
"import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health/db').read().decode())"
```

Expected:

```json
{"status":"ok","database":"reachable"}
```

---

# 35. Continuation Instruction for the Next Chat

Continue from the existing implementation.

Do **not** recreate:

```text
PostgreSQL deployment
Docker networks
FastAPI foundation
SQLAlchemy base
Alembic setup
Companies API
Contacts API
Leads API
Research API
Research Sources API
Research lifecycle
Research event logging
Migrations 001–003
Research lifecycle migration d62d40479f83
```

Research API MVP1 is complete and validated.

Current Research implementation:

```text
api/app/models/leads.py
api/app/schemas/research.py
api/app/services/research_service.py
api/app/routers/research.py
api/app/main.py
api/scripts/validate_research_api.py
```

Automated Research validation result:

```text
PASS: 80
FAIL: 0
SKIP: 1
RESULT: PASSED
```

Immediate next task:

```text
1. Review current LeadScore SQLAlchemy model.
2. Define Scoring API business rules.
3. Confirm score lifecycle and current-score behavior.
4. Create any required scoring migration after d62d40479f83.
5. Build scoring schemas.
6. Build scoring service.
7. Build scoring router.
8. Add scoring event logging.
9. Validate scoring end-to-end.
```

Preserve all existing architecture and business rules while continuing the build.

Do not integrate n8n yet.

The next authoritative build stage is:

```text
Scoring API
```
