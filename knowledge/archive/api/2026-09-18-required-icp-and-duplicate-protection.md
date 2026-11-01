> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Marketing API — Migration 003 Update

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**Update:** Migration 003 — Required ICP + Active Lead Duplicate Protection  
**Date:** 18 September 2026

---

# 1. Migration 003 Status

Migration `003` has been created and applied successfully.

Migration purpose:

```text
Require every lead to have an ICP
+
Prevent duplicate active leads at PostgreSQL level
```

Applied migration:

```text
002
 ↓
003
```

Migration name:

```text
require icp and prevent duplicate active leads
```

Alembic upgrade output confirmed:

```text
Running upgrade 002 -> 003, require icp and prevent duplicate active leads
```

---

# 2. ICP Is Now Mandatory

The MVP1 rule is now:

```text
Every lead must belong to one ICP.
```

The following layers were updated:

```text
FastAPI schema
    ↓
SQLAlchemy model
    ↓
PostgreSQL
```

## API Layer

`LeadCreate` now requires:

```python
icp_profile_id: UUID
```

It is no longer optional.

A request without `icp_profile_id` should now be rejected by FastAPI with:

```text
HTTP 422
```

## SQLAlchemy Layer

The `Lead` model now uses:

```python
icp_profile_id: Mapped[PyUUID] = mapped_column(
    UUID(as_uuid=True),
    ForeignKey(
        "icp_profiles.id",
        ondelete="RESTRICT",
    ),
    nullable=False,
)
```

The foreign key behavior changed from:

```text
ON DELETE SET NULL
```

to:

```text
ON DELETE RESTRICT
```

because an ICP can no longer become NULL while a lead still exists.

## PostgreSQL Verification

Verified:

```text
column_name      | is_nullable
-----------------+------------
icp_profile_id   | NO
```

Therefore:

```text
PostgreSQL NOT NULL enforcement = WORKING
```

---

# 3. Lead Duplicate Protection

The lead duplicate rule remains:

```text
company_id + icp_profile_id
```

`primary_contact_id` is intentionally not part of the duplicate rule.

Reason:

```text
A contact may change,
but the sales opportunity can remain the same.
```

---

# 4. API-Level Duplicate Protection

Already implemented before Migration 003.

The Marketing API checks for an existing active lead with the same:

```text
company_id
+
icp_profile_id
```

Active statuses:

```text
DISCOVERED
RESEARCHING
QUALIFIED
READY_FOR_OUTREACH
CONTACTED
REPLIED
```

If one already exists, the API returns:

```text
HTTP 409 Conflict
```

Example verified response:

```json
{
  "detail": {
    "message": "An active lead already exists for this company and ICP profile.",
    "existing_lead_id": "dcb7d435-cf8c-4202-868f-3666dc53f8ac",
    "existing_status": "DISCOVERED"
  }
}
```

The API duplicate check is therefore:

```text
WORKING
```

---

# 5. PostgreSQL-Level Duplicate Protection

Migration `003` added the partial unique index:

```text
idx_leads_active_company_icp_unique
```

Verified PostgreSQL index:

```text
CREATE UNIQUE INDEX idx_leads_active_company_icp_unique
ON public.leads
USING btree (company_id, icp_profile_id)
WHERE status IN (
    'DISCOVERED',
    'RESEARCHING',
    'QUALIFIED',
    'READY_FOR_OUTREACH',
    'CONTACTED',
    'REPLIED'
)
```

This means PostgreSQL itself now prevents:

```text
Same company
+
Same ICP
+
More than one active lead
```

even if two requests reach the database at nearly the same time.

Terminal lead statuses are excluded:

```text
CONVERTED
DISQUALIFIED
LOST
```

Therefore a future lead may be created for the same company + ICP after the previous opportunity reaches a terminal state.

---

# 6. Duplicate Protection Architecture

Duplicate protection now exists at two levels:

```text
POST /api/leads
        │
        ▼
Marketing API
        │
        ├── Check existing active lead
        │
        └── HTTP 409 if duplicate
        │
        ▼
PostgreSQL
        │
        └── Partial unique index
```

This gives:

```text
Friendly API validation
+
Hard database enforcement
```

---

# 7. Current Lead Rules

## Lead Creation

A lead now requires:

```text
company_id         REQUIRED
icp_profile_id     REQUIRED
primary_contact_id OPTIONAL
priority           LOW / MEDIUM / HIGH
```

New leads begin with:

```text
DISCOVERED
```

## Validation

The API verifies:

```text
Company exists                         ✓
Primary contact exists                 ✓
Primary contact belongs to company     ✓
ICP exists                             ✓
ICP is required                        ✓
Active duplicate does not exist        ✓
```

---

# 8. Lead Lifecycle

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

The active-lead unique index applies only while the lead is in:

```text
DISCOVERED
RESEARCHING
QUALIFIED
READY_FOR_OUTREACH
CONTACTED
REPLIED
```

---

# 9. Migration 003 Summary

```text
Migration 003
│
├── icp_profile_id nullable=False          ✓
├── PostgreSQL icp_profile_id NOT NULL     ✓
├── FK SET NULL → RESTRICT                 ✓
├── API requires ICP                       ✓
├── API active-lead duplicate check        ✓
└── PostgreSQL active-lead unique index    ✓
```

---

# 10. Final Alembic Verification

Recommended final checks:

```bash
docker exec lorrysystem-marketing-api alembic current
```

Expected:

```text
003 (head)
```

Then:

```bash
docker exec lorrysystem-marketing-api alembic check
```

Expected:

```text
No new upgrade operations detected.
```

These commands confirm that the SQLAlchemy models and PostgreSQL schema are fully synchronized after Migration 003.

---

# 11. Current API Coverage

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

# 12. Current Progress

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
├── 001 initial schema                       ✓
├── 002 seed catalog                         ✓
└── 003 ICP + active-lead uniqueness         ✓

Companies
├── Create                                   ✓
├── List                                     ✓
├── Get by UUID                              ✓
└── Duplicate protection                     ✓

Contacts
├── Create                                   ✓
├── List                                     ✓
├── Get by UUID                              ✓
├── Company relationship validation          ✓
└── Email duplicate protection               ✓

Leads
├── Create                                   ✓
├── List                                     ✓
├── Get by UUID                              ✓
├── Lifecycle transitions                    ✓
├── Event logging                            ✓
├── ICP mandatory                            ✓
├── API duplicate protection                 ✓
└── Database duplicate protection            ✓
```

---

# 13. Next Stage — Research

The next major API module is:

```text
/api/research
```

Existing tables:

```text
lead_research
research_sources
```

Required model changes next:

```text
Research statuses:
PENDING
RUNNING
COMPLETED
PARTIAL
FAILED
```

Add lifecycle timestamps:

```text
started_at
completed_at
```

Research history must be preserved:

```text
Lead
├── Research Run 1
├── Research Run 2
└── Research Run 3
```

Every research attempt creates a new `lead_research` record.

---

# 14. Planned Research API

Target routes:

```text
POST  /api/leads/{lead_id}/research
GET   /api/leads/{lead_id}/research

GET   /api/research/{research_id}

POST  /api/research/{research_id}/sources

PATCH /api/research/{research_id}/start
PATCH /api/research/{research_id}/complete
PATCH /api/research/{research_id}/fail
```

Possible later route:

```text
PATCH /api/research/{research_id}/partial
```

---

# 15. Research Workflow Target

```text
Lead created
    ↓
DISCOVERED
    ↓
Lead moves to RESEARCHING
    ↓
Research record created
    ↓
PENDING
    ↓
Automation starts
    ↓
RUNNING
    ↓
AI / web research
    ↓
Sources stored
    ↓
Findings stored
    ↓
COMPLETED
    ↓
Scoring stage
```

Important:

```text
Research COMPLETED
does NOT automatically mean
Lead QUALIFIED
```

Qualification happens later during the scoring stage.

---

# 16. Architecture Rule Still Applies

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

n8n must not connect directly to PostgreSQL.

Do not integrate n8n until the API business layer is stable.

---

# 17. Next Build Order

```text
Migration 003                            ✓
    ↓
ICP mandatory                            ✓
    ↓
Research model changes                   NEXT
    ↓
Research API
    ↓
Research source API
    ↓
Research lifecycle + events
    ↓
Scoring API
    ↓
Product matching
    ↓
Marketing actions
    ↓
Approval API
    ↓
n8n integration
    ↓
Marketing dashboard
```
