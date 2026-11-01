---
title: LorrySystem Marketing PostgreSQL Schema
project: LorrySystem AI Marketing & Lead Generation
version: 1.0
status: MVP1
tags:
  - lorrysystem
  - postgresql
  - database
  - marketing-api
  - mvp1
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Marketing PostgreSQL Schema — MVP1

## 1. Purpose

This document defines the **MVP1 PostgreSQL database design** for the LorrySystem AI Marketing & Lead Generation platform.

The database will store:

- Companies
- Contacts
- Leads
- ICP matches
- Research
- Research sources
- Lead scores
- Product matches
- Marketing actions
- Approval requests
- System events

The database must remain **private**.

> **Architecture rule:** n8n and the Marketing Dashboard must **not** connect directly to PostgreSQL.  
> Only the **Marketing API** should read from or write to PostgreSQL.

```text
n8n ───────────────┐
                   │ HTTP / JSON
                   ▼
            Marketing API
                   │
                   │ private DB connection
                   ▼
              PostgreSQL
                   ▲
                   │
Dashboard ─────────┘
```

---

# 2. MVP1 Docker Architecture

Recommended project path:

```text
/opt/
├── n8n/
│   ├── docker-compose.yml
│   ├── .env
│   ├── data/
│   └── secrets/
│
└── lorrysystem-marketing/
    ├── docker-compose.yml
    ├── .env
    ├── .env.example
    ├── data/
    │   └── postgres/
    ├── database/
    │   └── migrations/
    ├── api/
    ├── dashboard/
    ├── backups/
    └── docs/
```

For MVP1:

```text
Ubuntu VM
│
├── n8n container
├── cloudflared container
│
└── LorrySystem Marketing Stack
    ├── marketing-api
    ├── marketing-dashboard
    └── postgres
```

---

# 3. PostgreSQL Deployment

## Recommended PostgreSQL Container

```yaml
services:
  postgres:
    image: postgres:17-alpine
    container_name: lorrysystem-postgres
    restart: unless-stopped

    environment:
      POSTGRES_DB: ${POSTGRES_DB}
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}

    volumes:
      - ./data/postgres:/var/lib/postgresql/data

    healthcheck:
      test:
        [
          "CMD-SHELL",
          "pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}"
        ]
      interval: 10s
      timeout: 5s
      retries: 5

    networks:
      - lorrysystem-db-net

networks:
  lorrysystem-db-net:
    name: lorrysystem-db-net
    internal: true
```

## Important

Do **not** expose PostgreSQL with:

```yaml
ports:
  - "5432:5432"
```

PostgreSQL should not be reachable from:

- Internet
- LAN
- n8n directly
- Marketing Dashboard directly

Later the Marketing API container will join `lorrysystem-db-net`.

```text
marketing-api
      │
      ▼
postgres:5432
```

---

# 4. Environment Variables

Create:

```text
/opt/lorrysystem-marketing/.env
```

Example:

```env
POSTGRES_DB=lorrysystem_marketing
POSTGRES_USER=marketing_app
POSTGRES_PASSWORD=CHANGE_THIS_TO_A_LONG_RANDOM_PASSWORD
```

Also create `.env.example`:

```env
POSTGRES_DB=lorrysystem_marketing
POSTGRES_USER=marketing_app
POSTGRES_PASSWORD=CHANGE_ME
```

Add to `.gitignore`:

```gitignore
.env
data/
backups/
```

---

# 5. Schema Design Principles

## UUID Primary Keys

Use UUIDs instead of sequential IDs.

Example:

```text
7904f883-5db4-4de3-9ef0-5c1c4dd8e086
```

## Timezone-Aware Timestamps

Use:

```sql
TIMESTAMPTZ
```

## JSONB

Use `JSONB` for flexible information such as:

- AI research facts
- Pain points
- Buying signals
- Scoring breakdowns
- Metadata
- Qualification rules

Important searchable fields should remain normal columns.

---

# 6. Entity Relationship Overview

```text
products
    ▲
    │
product_matches
    │
    ▼
leads ─────────────► companies
 │                       │
 │                       └────► contacts
 │
 ├────► icp_profiles
 │
 ├────► lead_research
 │          │
 │          └────► research_sources
 │
 ├────► lead_scores
 │
 ├────► product_matches
 │
 └────► marketing_actions
              │
              └────► approval_requests

events
  │
  └── records activity across the platform
```

---

# 7. Table: `products`

Stores LorrySystem products that can be matched to leads.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| code | TEXT | Unique internal code |
| name | TEXT | Product name |
| category | TEXT | Product category |
| description | TEXT | Product description |
| active | BOOLEAN | Active/inactive |
| created_at | TIMESTAMPTZ | Creation time |
| updated_at | TIMESTAMPTZ | Last update |

Initial product codes:

```text
TMS
GPS
AI_DASHCAM
DMS
MDVR
FUEL_MONITORING
```

---

# 8. Table: `icp_profiles`

Stores Ideal Customer Profiles.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| code | TEXT | Unique ICP code |
| name | TEXT | ICP name |
| description | TEXT | ICP description |
| priority | INTEGER | Business priority |
| qualification_rules | JSONB | Flexible qualification rules |
| active | BOOLEAN | Active/inactive |
| created_at | TIMESTAMPTZ | Creation time |
| updated_at | TIMESTAMPTZ | Last update |

Initial ICP codes:

```text
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
COMMERCIAL_ENTERPRISE
```

Example:

```json
{
  "country": ["MY"],
  "industries": [
    "logistics",
    "haulage",
    "transport"
  ],
  "preferred_fleet_size": 10
}
```

---

# 9. Table: `companies`

Stores discovered companies.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| name | TEXT | Original company name |
| normalized_name | TEXT | Normalized name for duplicate detection |
| website_url | TEXT | Company website |
| domain | TEXT | Website domain |
| industry | TEXT | Industry/category |
| country_code | CHAR(2) | ISO country code |
| state | TEXT | State/region |
| city | TEXT | City |
| fleet_size_estimate | INTEGER | Estimated fleet size |
| fleet_size_confidence | INTEGER | 0–100 confidence |
| source_type | TEXT | Discovery source |
| source_url | TEXT | Original discovery URL |
| status | TEXT | Company record status |
| metadata | JSONB | Flexible metadata |
| created_at | TIMESTAMPTZ | Created |
| updated_at | TIMESTAMPTZ | Updated |

Deduplication should primarily use:

1. Domain
2. Normalized company name
3. Website
4. Existing contact data

---

# 10. Table: `contacts`

Stores people associated with companies.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| company_id | UUID | Foreign key → companies |
| full_name | TEXT | Contact name |
| job_title | TEXT | Role/title |
| email | TEXT | Email |
| phone | TEXT | Phone number |
| linkedin_url | TEXT | LinkedIn profile |
| is_primary | BOOLEAN | Primary contact |
| status | TEXT | Contact status |
| source_url | TEXT | Source of the contact |
| created_at | TIMESTAMPTZ | Created |
| updated_at | TIMESTAMPTZ | Updated |

---

# 11. Table: `leads`

Represents a marketing/sales opportunity.

A **company** is an organisation.  
A **lead** means that organisation may be a sales opportunity for LorrySystem.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| company_id | UUID | Foreign key → companies |
| primary_contact_id | UUID | Foreign key → contacts |
| icp_profile_id | UUID | Foreign key → icp_profiles |
| status | TEXT | Lead lifecycle status |
| priority | TEXT | LOW / MEDIUM / HIGH |
| current_score | INTEGER | Current 0–100 score |
| discovered_at | TIMESTAMPTZ | Lead discovery |
| qualified_at | TIMESTAMPTZ | Qualification |
| contacted_at | TIMESTAMPTZ | First contact |
| converted_at | TIMESTAMPTZ | Conversion |
| created_at | TIMESTAMPTZ | Created |
| updated_at | TIMESTAMPTZ | Updated |

Lead lifecycle:

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

---

# 12. Table: `lead_research`

Stores research runs for a lead.

Do not overwrite previous research. Each new research run creates a new row.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| lead_id | UUID | Foreign key → leads |
| summary | TEXT | Research summary |
| pain_points | JSONB | Identified pain points |
| buying_signals | JSONB | Buying signals |
| company_facts | JSONB | Structured facts |
| confidence | INTEGER | 0–100 |
| research_status | TEXT | COMPLETED / FAILED / PARTIAL |
| model_provider | TEXT | AI provider |
| model_name | TEXT | Model |
| raw_output | JSONB | Optional raw model result |
| researched_at | TIMESTAMPTZ | Research time |
| created_at | TIMESTAMPTZ | Created |

---

# 13. Table: `research_sources`

Stores evidence supporting lead research.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| research_id | UUID | Foreign key → lead_research |
| source_type | TEXT | WEBSITE / NEWS / SOCIAL / DIRECTORY |
| url | TEXT | Source URL |
| title | TEXT | Page/source title |
| evidence | TEXT | Relevant evidence |
| confidence | INTEGER | 0–100 |
| observed_at | TIMESTAMPTZ | Observation time |
| created_at | TIMESTAMPTZ | Created |

---

# 14. Table: `lead_scores`

Stores the history of lead scores.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| lead_id | UUID | Foreign key → leads |
| total_score | INTEGER | 0–100 |
| score_breakdown | JSONB | Breakdown of points |
| scoring_version | TEXT | Scoring algorithm version |
| rationale | TEXT | Human-readable explanation |
| is_current | BOOLEAN | Current score |
| created_at | TIMESTAMPTZ | Created |

Example:

```json
{
  "country_fit": 10,
  "industry_fit": 20,
  "fleet_size": 18,
  "decision_maker": 10,
  "buying_signal": 15,
  "product_fit": 14
}
```

---

# 15. Table: `product_matches`

Stores products relevant to each lead.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| lead_id | UUID | Foreign key → leads |
| product_id | UUID | Foreign key → products |
| fit_score | INTEGER | 0–100 |
| rationale | TEXT | Reason for match |
| created_at | TIMESTAMPTZ | Created |
| updated_at | TIMESTAMPTZ | Updated |

---

# 16. Table: `marketing_actions`

Stores actions generated by the system.

Examples:

- Email
- Follow-up
- LinkedIn comment
- Facebook post
- Instagram post
- X post
- Direct message

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| lead_id | UUID | Optional foreign key → leads |
| contact_id | UUID | Optional foreign key → contacts |
| channel | TEXT | EMAIL / LINKEDIN / FACEBOOK / INSTAGRAM / X |
| action_type | TEXT | EMAIL / POST / COMMENT / FOLLOW_UP / DIRECT_MESSAGE |
| subject | TEXT | Optional subject |
| content | TEXT | Generated content |
| status | TEXT | Action status |
| scheduled_at | TIMESTAMPTZ | Scheduled execution |
| executed_at | TIMESTAMPTZ | Execution time |
| external_reference | TEXT | Provider/message/post ID |
| created_by | TEXT | Workflow/user source |
| created_at | TIMESTAMPTZ | Created |
| updated_at | TIMESTAMPTZ | Updated |

Action lifecycle:

```text
DRAFT
    ↓
PENDING_APPROVAL
    ↓
APPROVED
    ↓
QUEUED
    ↓
SENT / PUBLISHED
```

Alternative states:

```text
REJECTED
FAILED
CANCELLED
```

---

# 17. Table: `approval_requests`

Stores human approval decisions.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| marketing_action_id | UUID | Foreign key → marketing_actions |
| status | TEXT | Approval status |
| requested_at | TIMESTAMPTZ | Requested time |
| decided_by | TEXT | Reviewer |
| decided_at | TIMESTAMPTZ | Decision time |
| reviewer_notes | TEXT | Notes |
| content_snapshot | JSONB | Exact content being approved |
| created_at | TIMESTAMPTZ | Created |
| updated_at | TIMESTAMPTZ | Updated |

Statuses:

```text
PENDING
APPROVED
REJECTED
CHANGES_REQUESTED
```

---

# 18. Table: `events`

Stores activity history.

| Column | Type | Notes |
|---|---|---|
| id | UUID | Primary key |
| event_type | TEXT | Event name |
| entity_type | TEXT | COMPANY / LEAD / ACTION / APPROVAL etc. |
| entity_id | UUID | Entity reference |
| actor_type | TEXT | SYSTEM / N8N / USER / API |
| actor_id | TEXT | Actor reference/name |
| metadata | JSONB | Additional event data |
| created_at | TIMESTAMPTZ | Event time |

Example event types:

```text
company_created
lead_discovered
research_started
research_completed
lead_scored
lead_qualified
email_generated
approval_requested
approval_approved
email_sent
email_replied
```

---

# 19. Recommended Indexes

```sql
CREATE INDEX idx_companies_normalized_name
ON companies (normalized_name);

CREATE UNIQUE INDEX idx_companies_domain_unique
ON companies (LOWER(domain))
WHERE domain IS NOT NULL;

CREATE INDEX idx_contacts_company_id
ON contacts (company_id);

CREATE UNIQUE INDEX idx_contacts_email_unique
ON contacts (LOWER(email))
WHERE email IS NOT NULL;

CREATE INDEX idx_leads_company_id
ON leads (company_id);

CREATE INDEX idx_leads_status
ON leads (status);

CREATE INDEX idx_leads_current_score
ON leads (current_score DESC);

CREATE INDEX idx_lead_research_lead_id
ON lead_research (lead_id);

CREATE INDEX idx_research_sources_research_id
ON research_sources (research_id);

CREATE INDEX idx_lead_scores_lead_id
ON lead_scores (lead_id);

CREATE UNIQUE INDEX idx_lead_scores_one_current
ON lead_scores (lead_id)
WHERE is_current = TRUE;

CREATE UNIQUE INDEX idx_product_matches_unique
ON product_matches (lead_id, product_id);

CREATE INDEX idx_marketing_actions_status
ON marketing_actions (status);

CREATE INDEX idx_marketing_actions_lead
ON marketing_actions (lead_id);

CREATE INDEX idx_approval_requests_status
ON approval_requests (status);

CREATE INDEX idx_events_created_at
ON events (created_at DESC);

CREATE INDEX idx_events_event_type
ON events (event_type);
```

---

# 20. Target SQL Schema

> This SQL is a **reference schema**.  
> Recommended implementation is to let the Marketing API create/manage the schema using **SQLAlchemy + Alembic migrations**.

```sql
CREATE TABLE products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    category TEXT,
    description TEXT,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE icp_profiles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    description TEXT,
    priority INTEGER NOT NULL DEFAULT 0,
    qualification_rules JSONB NOT NULL DEFAULT '{}'::jsonb,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE companies (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    normalized_name TEXT,
    website_url TEXT,
    domain TEXT,
    industry TEXT,
    country_code CHAR(2),
    state TEXT,
    city TEXT,
    fleet_size_estimate INTEGER CHECK (fleet_size_estimate >= 0),
    fleet_size_confidence INTEGER CHECK (
        fleet_size_confidence BETWEEN 0 AND 100
    ),
    source_type TEXT,
    source_url TEXT,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL
        REFERENCES companies(id) ON DELETE CASCADE,
    full_name TEXT NOT NULL,
    job_title TEXT,
    email TEXT,
    phone TEXT,
    linkedin_url TEXT,
    is_primary BOOLEAN NOT NULL DEFAULT FALSE,
    status TEXT NOT NULL DEFAULT 'ACTIVE',
    source_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE leads (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    company_id UUID NOT NULL
        REFERENCES companies(id) ON DELETE CASCADE,
    primary_contact_id UUID
        REFERENCES contacts(id) ON DELETE SET NULL,
    icp_profile_id UUID
        REFERENCES icp_profiles(id) ON DELETE SET NULL,
    status TEXT NOT NULL DEFAULT 'DISCOVERED',
    priority TEXT NOT NULL DEFAULT 'MEDIUM',
    current_score INTEGER CHECK (
        current_score BETWEEN 0 AND 100
    ),
    discovered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    qualified_at TIMESTAMPTZ,
    contacted_at TIMESTAMPTZ,
    converted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE lead_research (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL
        REFERENCES leads(id) ON DELETE CASCADE,
    summary TEXT,
    pain_points JSONB NOT NULL DEFAULT '[]'::jsonb,
    buying_signals JSONB NOT NULL DEFAULT '[]'::jsonb,
    company_facts JSONB NOT NULL DEFAULT '{}'::jsonb,
    confidence INTEGER CHECK (
        confidence BETWEEN 0 AND 100
    ),
    research_status TEXT NOT NULL DEFAULT 'COMPLETED',
    model_provider TEXT,
    model_name TEXT,
    raw_output JSONB,
    researched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE research_sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    research_id UUID NOT NULL
        REFERENCES lead_research(id) ON DELETE CASCADE,
    source_type TEXT,
    url TEXT NOT NULL,
    title TEXT,
    evidence TEXT,
    confidence INTEGER CHECK (
        confidence BETWEEN 0 AND 100
    ),
    observed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE lead_scores (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL
        REFERENCES leads(id) ON DELETE CASCADE,
    total_score INTEGER NOT NULL CHECK (
        total_score BETWEEN 0 AND 100
    ),
    score_breakdown JSONB NOT NULL DEFAULT '{}'::jsonb,
    scoring_version TEXT NOT NULL,
    rationale TEXT,
    is_current BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE product_matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID NOT NULL
        REFERENCES leads(id) ON DELETE CASCADE,
    product_id UUID NOT NULL
        REFERENCES products(id) ON DELETE CASCADE,
    fit_score INTEGER NOT NULL CHECK (
        fit_score BETWEEN 0 AND 100
    ),
    rationale TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (lead_id, product_id)
);

CREATE TABLE marketing_actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id UUID
        REFERENCES leads(id) ON DELETE SET NULL,
    contact_id UUID
        REFERENCES contacts(id) ON DELETE SET NULL,
    channel TEXT NOT NULL,
    action_type TEXT NOT NULL,
    subject TEXT,
    content TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'DRAFT',
    scheduled_at TIMESTAMPTZ,
    executed_at TIMESTAMPTZ,
    external_reference TEXT,
    created_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE approval_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    marketing_action_id UUID NOT NULL
        REFERENCES marketing_actions(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'PENDING',
    requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    decided_by TEXT,
    decided_at TIMESTAMPTZ,
    reviewer_notes TEXT,
    content_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_type TEXT NOT NULL,
    entity_type TEXT,
    entity_id UUID,
    actor_type TEXT,
    actor_id TEXT,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
```

---

# 21. Initial Seed Data

Initial products:

```text
TMS
GPS
AI_DASHCAM
DMS
MDVR
FUEL_MONITORING
```

Initial ICPs:

```text
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
COMMERCIAL_ENTERPRISE
```

Seed data should eventually be handled by migrations or a controlled seed script.

---

# 22. Migration Strategy

Recommended stack:

```text
Marketing API
      │
      ├── Python
      ├── FastAPI
      ├── SQLAlchemy
      └── Alembic
            │
            ▼
        PostgreSQL
```

Example migration structure:

```text
database/
└── migrations/
    └── versions/
        ├── 001_initial_schema.py
        ├── 002_add_competitors.py
        └── ...
```

When moving to the cloud:

```bash
alembic upgrade head
```

---

# 23. Backup Strategy

Example logical backup:

```bash
docker exec lorrysystem-postgres   pg_dump   -U marketing_app   -d lorrysystem_marketing   -Fc   > backups/lorrysystem_marketing.dump
```

Restore will use `pg_restore` against the new PostgreSQL environment.

---

# 24. MVP1 Database Rules

```text
n8n       ✕ PostgreSQL
Dashboard ✕ PostgreSQL
Internet  ✕ PostgreSQL

Marketing API ✓ PostgreSQL
```

Business rules belong in the Marketing API.

Examples:

- Duplicate detection
- Lead status transitions
- Current lead score handling
- Product matching
- Approval validation
- Event logging

PostgreSQL remains the persistent storage layer.

---

# 25. Tables Deferred Until Later

Do not add these until required:

```text
campaigns
competitors
competitor_observations
social_analytics
video_assets
users
roles
permissions
crm_sync
embeddings
vector_search
billing
```

Likely next additions during MVP1:

```text
competitors
competitor_observations
```

Likely MVP2 additions:

```text
campaigns
content_calendar
channel_accounts
email_delivery_events
```

---

# 26. Deployment Sequence

```text
1. Back up existing n8n VM
        ↓
2. Create /opt/lorrysystem-marketing
        ↓
3. Create .env
        ↓
4. Create Docker Compose
        ↓
5. Start PostgreSQL
        ↓
6. Confirm health check
        ↓
7. Confirm persistent storage
        ↓
8. Build Marketing API
        ↓
9. Add SQLAlchemy models
        ↓
10. Add Alembic migrations
        ↓
11. Run initial migration
        ↓
12. Seed products + ICPs
        ↓
13. Test API → PostgreSQL
        ↓
14. Connect n8n → Marketing API
```

---

# 27. MVP1 Success Check

The database layer is ready when:

- PostgreSQL starts successfully.
- Health check reports healthy.
- Data survives container restarts.
- PostgreSQL is not exposed publicly.
- Only the Marketing API can access the database network.
- Alembic can create the schema from an empty database.
- Products and ICP seed data can be loaded.
- The database can be backed up and restored.
- n8n communicates only through the Marketing API.

---

# Next Step

After PostgreSQL is running, build:

```text
Marketing API
│
├── FastAPI
├── SQLAlchemy
├── Alembic
└── PostgreSQL driver
```

Initial API modules:

```text
/api/companies
/api/contacts
/api/leads
/api/research
/api/approvals
/api/actions
/api/events
```
