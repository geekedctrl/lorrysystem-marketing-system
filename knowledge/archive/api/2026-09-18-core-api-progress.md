> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Marketing API — Progress Update

**File:** `api-update.md`  
**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**Last updated:** 18 September 2026

---

## 1. Current Architecture

```text
n8n
└── n8n_default

Marketing API
├── lorrysystem-api-net
└── lorrysystem-db-net
        │
        ▼
    PostgreSQL
    └── lorrysystem-db-net
```

### Architecture Rules

- n8n does **not** connect directly to PostgreSQL.
- PostgreSQL is **not exposed** to the host, LAN, or Internet.
- Only the Marketing API is allowed to access PostgreSQL.
- n8n will eventually communicate with the Marketing API over HTTP/JSON.
- Business logic stays inside the Marketing API.
- PostgreSQL is used as the persistent storage layer.

---

# 2. PostgreSQL Deployment

## Completed

- PostgreSQL deployed in Docker.
- Image: `postgres:17-alpine`
- Container: `lorrysystem-postgres`
- Database: `lorrysystem_marketing`
- Application DB user: `marketing_app`
- Persistent storage configured at:

```text
/opt/lorrysystem-marketing/data/postgres
```

- PostgreSQL health check is working.
- Database login tested successfully.
- Persistent storage tested successfully across container restart.
- PostgreSQL port `5432` is **not published** to the host.
- Private Docker network created:

```text
lorrysystem-db-net
```

- Network confirmed:

```text
Internal=true
```

- Only `lorrysystem-postgres` and `lorrysystem-marketing-api` are attached to the database network.
- `n8n` remains isolated on:

```text
n8n_default
```

---

# 3. Project Folder Structure

Current project root:

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
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── routers/
│   │   ├── schemas/
│   │   └── services/
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

# 4. Marketing API Foundation

## Stack

- Python
- FastAPI
- Uvicorn
- SQLAlchemy 2.x
- Alembic
- Psycopg 3
- Pydantic Settings

## Container

```text
lorrysystem-marketing-api
```

## Networks

The Marketing API is attached to:

```text
lorrysystem-api-net
lorrysystem-db-net
```

## Health Endpoints

Implemented:

```text
GET /health
GET /health/db
```

Verified:

```json
{"status":"ok","database":"reachable"}
```

This confirms:

```text
FastAPI
   ↓
SQLAlchemy
   ↓
Psycopg
   ↓
PostgreSQL
```

---

# 5. SQLAlchemy Models

The initial SQLAlchemy model layer has been created for:

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

Total application tables:

```text
12
```

---

# 6. Alembic

## Migration 001

Created and applied:

```text
001_initial_schema.py
```

Purpose:

- Creates the initial 12-table PostgreSQL schema.
- Creates foreign keys.
- Creates indexes.
- Creates validation constraints.
- Creates the Alembic version tracking table.

Verified with:

```bash
alembic current
```

Result:

```text
001 (head)
```

## Migration 002

Created and applied:

```text
002_seed_initial_catalog.py
```

Seeded products:

```text
TMS
GPS
AI_DASHCAM
DMS
MDVR
FUEL_MONITORING
```

Seeded ICP profiles:

```text
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
COMMERCIAL_ENTERPRISE
```

## Alembic Synchronization

Verified with:

```bash
alembic check
```

Result:

```text
No new upgrade operations detected.
```

---

# 7. Companies API

Implemented:

```text
POST /api/companies
GET  /api/companies
GET  /api/companies/{company_id}
```

## Company Creation

Verified successfully through:

```text
FastAPI
   ↓
Company service
   ↓
SQLAlchemy
   ↓
PostgreSQL
```

Test company created:

```text
Test Logistics Sdn Bhd
```

## Company Duplicate Protection

Implemented at the API layer.

Duplicate checks currently use:

1. Domain
2. Normalized company name
3. Website URL

Example behavior:

```text
POST duplicate company
        ↓
HTTP 409 Conflict
```

Verified:

```text
Company already exists (matched by domain).
```

PostgreSQL row count remained unchanged after duplicate request.

## Database-Level Company Protection

The schema already contains a case-insensitive unique index for company domain:

```text
idx_companies_domain_unique
```

Therefore company duplication protection exists at both:

```text
API layer
+
Database layer for domain uniqueness
```

---

# 8. Contacts API

Implemented:

```text
POST /api/contacts
GET  /api/contacts
GET  /api/contacts/{contact_id}
GET  /api/contacts?company_id=<uuid>
```

## Contact Validation

Implemented:

- Company must exist.
- Contact is linked to a company.
- Email is normalized to lowercase.
- Duplicate email is checked before insertion.
- PostgreSQL also has a case-insensitive unique email index.

## Test Contact

Created successfully:

```text
Name:       John Tan
Job title:  Fleet Manager
Primary:    true
Status:     ACTIVE
```

Verified using a PostgreSQL JOIN:

```text
Test Logistics Sdn Bhd
└── John Tan
    └── Fleet Manager
```

---

# 9. Leads API

Implemented:

```text
POST  /api/leads
GET   /api/leads
GET   /api/leads/{lead_id}
PATCH /api/leads/{lead_id}/status
```

## Lead Creation Validation

The API currently validates:

- Company exists.
- Primary contact exists.
- Primary contact belongs to the selected company.
- ICP profile exists.
- Priority is restricted to:

```text
LOW
MEDIUM
HIGH
```

New leads begin with:

```text
DISCOVERED
```

## Lead Lifecycle

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

Alternative terminal exits:

```text
DISQUALIFIED
LOST
```

The API prevents invalid status jumps.

Lifecycle timestamps are managed by the API:

```text
qualified_at
contacted_at
converted_at
```

---

# 10. Lead Event Logging

Creating a lead generates an event:

```text
lead_discovered
```

Lead lifecycle changes also generate events.

Events contain:

```text
event_type
entity_type
entity_id
actor_type
actor_id
metadata
created_at
```

Business event logging is handled by the Marketing API.

---

# 11. Lead Duplicate Protection

## API-Level Protection — COMPLETED

Current duplicate rule:

```text
One active lead per:

company_id + icp_profile_id
```

The primary contact is deliberately **not** part of lead uniqueness because a contact can change while the sales opportunity remains the same.

Active statuses:

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

After a lead reaches a terminal state, a future lead for the same company + ICP may be created.

## Verified Behavior

Repeated POST request returned:

```text
HTTP 409 Conflict
```

Response:

```json
{
  "detail": {
    "message": "An active lead already exists for this company and ICP profile.",
    "existing_lead_id": "dcb7d435-cf8c-4202-868f-3666dc53f8ac",
    "existing_status": "DISCOVERED"
  }
}
```

PostgreSQL confirmed that only one matching active lead remained.

## Database-Level Lead Protection — NEXT

The API duplicate check is complete.

Still to add:

```text
PostgreSQL partial unique index
```

Planned index:

```text
idx_leads_active_company_icp_unique
```

Purpose:

- Prevent race-condition duplicates.
- Enforce one active lead per company + ICP directly in PostgreSQL.
- Complement the API-level duplicate check.

This should be introduced through:

```text
003_prevent_duplicate_active_leads.py
```

---

# 12. Current Duplicate Protection Summary

| Resource | API Protection | Database Protection | Status |
|---|---|---|---|
| Companies | Domain, normalized name, website | Unique domain index | Working |
| Contacts | Email | Unique case-insensitive email index | Working |
| Leads | Company + ICP for active leads | Pending unique active-lead index | API working / DB pending |

---

# 13. Current API Routes

```text
GET    /
GET    /health
GET    /health/db

POST   /api/companies
GET    /api/companies
GET    /api/companies/{company_id}

POST   /api/contacts
GET    /api/contacts
GET    /api/contacts/{contact_id}

POST   /api/leads
GET    /api/leads
GET    /api/leads/{lead_id}
PATCH  /api/leads/{lead_id}/status
```

---

# 14. Current MVP1 Progress

```text
Infrastructure
├── PostgreSQL Docker deployment             ✓
├── Persistent PostgreSQL storage            ✓
├── Private DB network                       ✓
├── PostgreSQL not publicly exposed          ✓
├── Marketing API Docker deployment          ✓
├── API network                              ✓
├── API → PostgreSQL connectivity            ✓
└── n8n isolated from PostgreSQL             ✓

Database
├── SQLAlchemy model layer                   ✓
├── Alembic configured                       ✓
├── 001 initial schema                       ✓
├── 002 seed catalog                         ✓
├── Products seeded                          ✓
├── ICP profiles seeded                      ✓
└── 003 active-lead uniqueness               NEXT

API
├── Health                                   ✓
├── Database health                          ✓
├── Companies                                ✓
├── Company duplicate detection              ✓
├── Contacts                                 ✓
├── Contact duplicate email protection       ✓
├── Leads                                    ✓
├── Lead lifecycle validation                ✓
├── Lead event logging                       ✓
└── Lead API duplicate detection             ✓
```

---

# 15. Recommended Next Steps

## Immediate Next Step

Add database-level duplicate protection for active leads:

```text
SQLAlchemy partial unique index
        ↓
Alembic migration 003
        ↓
alembic upgrade head
        ↓
alembic check
```

## After Migration 003

Build:

```text
/api/research
```

using:

```text
lead_research
research_sources
```

The research layer should support:

- Starting a research run for a lead.
- Saving research history instead of overwriting previous research.
- Research summaries.
- Pain points.
- Buying signals.
- Company facts.
- Confidence score.
- Model provider.
- Model name.
- Raw AI output.
- Evidence/source URLs.
- Research status.
- Event logging.

## Later MVP1 Stages

```text
/api/research
        ↓
/api/scoring
        ↓
product matching
        ↓
/api/actions
        ↓
/api/approvals
        ↓
n8n integration
        ↓
marketing dashboard
```

---

# 16. Important Design Principle

The intended architecture remains:

```text
n8n
  │
  │ HTTP / JSON
  ▼
Marketing API
  │
  │ SQLAlchemy
  ▼
PostgreSQL
```

Not:

```text
n8n
  │
  ✕
PostgreSQL
```

All business rules, duplicate detection, lifecycle transitions, validation, scoring logic, approval logic, and event logging should remain in the Marketing API.

