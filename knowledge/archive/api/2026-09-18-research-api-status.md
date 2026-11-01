---
title: LorrySystem Research API
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
date: 2026-09-18
status: in-progress
priority: critical
tags:
  - lorrysystem
  - research-api
  - fastapi
  - postgresql
  - sqlalchemy
  - alembic
  - n8n
  - mvp1
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Research API — MVP1

## 1. Purpose

The Research API is the **core intelligence layer** of the LorrySystem Marketing Platform.

Its job is to manage the research process for each lead before scoring, product matching, outreach, and approval.

The Research API should answer questions such as:

```text
Who is this company?

What does the company do?

How large is the fleet?

What industry is it in?

What pain points can be identified?

Are there buying signals?

Who are the likely decision makers?

Which facts are confirmed?

Which facts are only estimates?

Where did the information come from?

How confident are we in the research?
```

The Research API does **not** directly perform web research by itself.

The intended architecture is:

```text
n8n / Research Automation
        │
        │ HTTP / JSON
        ▼
    Research API
        │
        │ SQLAlchemy
        ▼
    PostgreSQL
```

The Research API is responsible for:

- Creating research runs
- Managing research lifecycle
- Storing research findings
- Storing research evidence/sources
- Preserving historical research
- Validating research state transitions
- Logging research events
- Preparing research output for scoring
- Providing research data to the dashboard
- Providing a stable API contract for n8n later

---

# 2. Architecture Rule

The existing architecture remains unchanged:

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

Rules:

```text
n8n       ✕ PostgreSQL
Dashboard ✕ PostgreSQL
Internet  ✕ PostgreSQL

Marketing API ✓ PostgreSQL
```

The Research API is part of the Marketing API.

---

# 3. Research Is Separate From Qualification

Important rule:

```text
Research completed
≠
Lead qualified
```

Research only gathers and structures evidence.

Qualification happens later through:

```text
Research
    ↓
Scoring
    ↓
Product Matching
    ↓
QUALIFIED / DISQUALIFIED
```

Therefore:

```text
COMPLETED research
```

must not automatically set the lead to:

```text
QUALIFIED
```

---

# 4. Research History Must Be Preserved

Each research attempt creates a **new research run**.

Do not overwrite previous research.

Example:

```text
Lead: ABC Logistics
│
├── Research Run 1
│   ├── Initial company discovery
│   └── 18 Sep 2026
│
├── Research Run 2
│   ├── Manual refresh
│   └── 25 Sep 2026
│
└── Research Run 3
    ├── Pre-outreach refresh
    └── 05 Oct 2026
```

This allows the platform to track:

- What was known at each point in time
- What changed
- Which model generated the research
- Which sources supported the result
- Whether confidence improved or declined

---

# 5. Research Lifecycle

Use the following research statuses:

```text
PENDING
RUNNING
COMPLETED
PARTIAL
FAILED
```

## Status Meaning

### `PENDING`

Research record exists but work has not started.

```text
Research requested
        ↓
PENDING
```

### `RUNNING`

Research automation has started.

```text
PENDING
   ↓
RUNNING
```

### `COMPLETED`

Research completed successfully.

```text
RUNNING
   ↓
COMPLETED
```

### `PARTIAL`

Useful research was collected, but some required information could not be found.

```text
RUNNING
   ↓
PARTIAL
```

### `FAILED`

Research could not be completed.

```text
RUNNING
   ↓
FAILED
```

---

# 6. Allowed Research Status Transitions

Recommended transitions:

```text
PENDING → RUNNING

RUNNING → COMPLETED
RUNNING → PARTIAL
RUNNING → FAILED
```

Optional later:

```text
FAILED → PENDING
```

for retry behavior.

Invalid examples:

```text
PENDING → COMPLETED      ✕
COMPLETED → RUNNING      ✕
FAILED → COMPLETED       ✕
```

The Marketing API must reject invalid status transitions.

---

# 7. Lead Lifecycle Integration

When research begins:

```text
Lead:
DISCOVERED
    ↓
RESEARCHING
```

When research ends:

```text
RESEARCHING
    ↓
Research completed
    ↓
Scoring stage
```

Do not move the lead to:

```text
QUALIFIED
```

until scoring is complete.

---

# 8. `lead_research` Model

The current `lead_research` table should support:

| Field | Type | Purpose |
|---|---|---|
| id | UUID | Research run ID |
| lead_id | UUID | Lead being researched |
| research_status | TEXT | PENDING / RUNNING / COMPLETED / PARTIAL / FAILED |
| summary | TEXT | Human-readable research summary |
| pain_points | JSONB | Identified business pain points |
| buying_signals | JSONB | Signals suggesting possible purchase intent |
| company_facts | JSONB | Structured company facts |
| confidence | INTEGER | Overall research confidence 0–100 |
| model_provider | TEXT | AI provider used |
| model_name | TEXT | AI model used |
| raw_output | JSONB | Optional original structured AI output |
| started_at | TIMESTAMPTZ | Research start |
| completed_at | TIMESTAMPTZ | Research completion |
| created_at | TIMESTAMPTZ | Research record creation |

Optional later:

```text
research_trigger
```

Possible values:

```text
INITIAL_DISCOVERY
MANUAL_REFRESH
SCHEDULED_REFRESH
PRE_OUTREACH_REFRESH
```

---

# 9. `research_sources` Model

Each research run may contain multiple sources.

| Field | Type | Purpose |
|---|---|---|
| id | UUID | Source ID |
| research_id | UUID | Foreign key to research run |
| source_type | TEXT | Source category |
| url | TEXT | Source URL |
| title | TEXT | Source/page title |
| evidence | TEXT | Relevant evidence extracted |
| confidence | INTEGER | Confidence in source/evidence |
| observed_at | TIMESTAMPTZ | When the source was observed |
| created_at | TIMESTAMPTZ | Row creation time |

Recommended source types:

```text
WEBSITE
NEWS
SOCIAL
DIRECTORY
SEARCH
OTHER
```

---

# 10. Research Data Structure

A research result should be able to represent:

```json
{
  "summary": "ABC Logistics is a Malaysian haulage company operating commercial transport services.",
  "pain_points": [
    "fleet visibility",
    "driver safety",
    "manual delivery coordination"
  ],
  "buying_signals": [
    "recent fleet expansion",
    "hiring additional drivers"
  ],
  "company_facts": {
    "country": "MY",
    "state": "Selangor",
    "industry": "haulage",
    "fleet_size_estimate": 50,
    "fleet_size_confidence": 75
  },
  "confidence": 84
}
```

---

# 11. Evidence Principle

Important claims should be supported by source evidence.

Example:

```text
Claim:
Fleet size approximately 50 vehicles

Source:
Company website

Evidence:
"Operating a fleet of more than 50 commercial vehicles"

URL:
https://example.com/fleet
```

The system should distinguish between:

```text
confirmed fact
estimated fact
AI inference
```

This distinction may later be represented through:

```text
confidence
source_type
evidence
```

or a future structured fact model.

---

# 12. Recommended API Routes

## Create Research Run

```text
POST /api/leads/{lead_id}/research
```

Purpose:

- Verify lead exists
- Create new research run
- Set research status to `PENDING`
- Move lead to `RESEARCHING` if valid
- Generate `research_requested` event

Expected result:

```json
{
  "id": "<research_uuid>",
  "lead_id": "<lead_uuid>",
  "research_status": "PENDING"
}
```

---

## List Research Runs for Lead

```text
GET /api/leads/{lead_id}/research
```

Purpose:

Return all research history for the selected lead.

Recommended order:

```text
newest first
```

---

## Get Research Run

```text
GET /api/research/{research_id}
```

Purpose:

Return:

- Research findings
- Research status
- Confidence
- AI metadata
- Sources
- Lifecycle timestamps

---

## Start Research

```text
PATCH /api/research/{research_id}/start
```

Expected transition:

```text
PENDING → RUNNING
```

Actions:

- Set `started_at`
- Set status `RUNNING`
- Generate `research_started` event

---

## Add Research Source

```text
POST /api/research/{research_id}/sources
```

Purpose:

Add source/evidence to the research run.

Actions:

- Validate research exists
- Validate URL/input
- Insert source
- Generate `research_source_added` event

---

## Complete Research

```text
PATCH /api/research/{research_id}/complete
```

Purpose:

Store final findings and mark research complete.

Expected transition:

```text
RUNNING → COMPLETED
```

Actions:

- Validate research is `RUNNING`
- Store summary
- Store pain points
- Store buying signals
- Store company facts
- Store confidence
- Store model metadata
- Store raw output if enabled
- Set `completed_at`
- Generate `research_completed` event

Important:

```text
Lead remains unqualified until scoring.
```

---

## Mark Research Partial

Recommended route:

```text
PATCH /api/research/{research_id}/partial
```

Transition:

```text
RUNNING → PARTIAL
```

Use when:

- Some information was found
- Critical fields are missing
- Research is still useful enough for later processing

---

## Fail Research

```text
PATCH /api/research/{research_id}/fail
```

Transition:

```text
RUNNING → FAILED
```

Recommended payload:

```json
{
  "reason": "Unable to access enough reliable company information."
}
```

Actions:

- Set status `FAILED`
- Set `completed_at`
- Log failure reason in event metadata
- Generate `research_failed` event

---

# 13. Research Events

Recommended event types:

```text
research_requested
research_started
research_source_added
research_completed
research_partial
research_failed
```

Example:

```json
{
  "event_type": "research_completed",
  "entity_type": "RESEARCH",
  "entity_id": "<research_uuid>",
  "actor_type": "API",
  "metadata": {
    "lead_id": "<lead_uuid>",
    "confidence": 86,
    "source_count": 5
  }
}
```

---

# 14. Research Validation Rules

The API should validate:

## Create Research

```text
Lead exists                     ✓
Lead is not terminal            ✓
Lead status allows research     ✓
New research run can be created ✓
```

## Start Research

```text
Research exists                 ✓
Current status = PENDING        ✓
started_at not already set      ✓
```

## Add Source

```text
Research exists                 ✓
URL provided                    ✓
Confidence between 0–100        ✓
```

## Complete Research

```text
Research exists                 ✓
Current status = RUNNING        ✓
Confidence between 0–100        ✓
Required result structure valid ✓
```

## Fail Research

```text
Research exists                 ✓
Current status = RUNNING        ✓
Failure reason recorded         ✓
```

---

# 15. Suggested Pydantic Schemas

Recommended schema classes:

```text
ResearchCreate
ResearchRead
ResearchSummary
ResearchComplete
ResearchFail
ResearchSourceCreate
ResearchSourceRead
```

Possible structure:

```python
class ResearchComplete(BaseModel):
    summary: str
    pain_points: list[str] = []
    buying_signals: list[str] = []
    company_facts: dict = {}
    confidence: int
    model_provider: str | None = None
    model_name: str | None = None
    raw_output: dict | None = None
```

Validation:

```text
confidence >= 0
confidence <= 100
```

---

# 16. Suggested Service Layer

Create:

```text
api/app/services/research_service.py
```

Suggested responsibilities:

```text
create_research_run()
get_research()
list_research_for_lead()
start_research()
add_research_source()
complete_research()
mark_research_partial()
fail_research()
validate_research_transition()
```

Do not place business logic directly inside FastAPI routers.

---

# 17. Suggested Router Structure

Create:

```text
api/app/routers/research.py
```

Router responsibility:

```text
HTTP request
    ↓
Pydantic validation
    ↓
Research service
    ↓
SQLAlchemy
    ↓
PostgreSQL
```

Router should remain thin.

---

# 18. Recommended Model Migration

The existing research model needs:

```text
PENDING
RUNNING
COMPLETED
PARTIAL
FAILED

started_at
completed_at
```

Create a new Alembic migration after `003`.

Suggested migration:

```text
004_research_lifecycle.py
```

Migration responsibilities:

- Add/confirm research lifecycle fields
- Add `started_at`
- Add `completed_at`
- Update defaults if required
- Add indexes if useful
- Keep existing data compatible

---

# 19. Recommended Indexes

Consider:

```sql
CREATE INDEX idx_lead_research_lead_id
ON lead_research (lead_id);

CREATE INDEX idx_lead_research_status
ON lead_research (research_status);

CREATE INDEX idx_lead_research_created_at
ON lead_research (created_at DESC);

CREATE INDEX idx_research_sources_research_id
ON research_sources (research_id);
```

---

# 20. Recommended Research Workflow Before n8n

First test manually through FastAPI.

```text
1. Create lead
2. Create research run
3. Start research
4. Add research source
5. Add another source
6. Complete research
7. Retrieve research
8. Verify research history
9. Verify events
10. Verify lead is still not QUALIFIED
```

Only after this flow works should n8n be connected.

---

# 21. Future n8n Research Workflow

Once the API is stable:

```text
n8n Schedule / Trigger
        ↓
GET leads requiring research
        ↓
POST /api/leads/{id}/research
        ↓
PATCH /api/research/{id}/start
        ↓
Web/Data Collection
        ↓
AI Research
        ↓
POST research sources
        ↓
PATCH /api/research/{id}/complete
        ↓
Trigger scoring workflow
```

n8n should never directly update:

```text
lead_research
research_sources
leads
events
```

through SQL.

Everything goes through the API.

---

# 22. Research API Progress Tracker

## Database / Migration

- [ ] Review current `lead_research` model
- [ ] Add `PENDING`
- [ ] Add `RUNNING`
- [ ] Confirm `COMPLETED`
- [ ] Confirm `PARTIAL`
- [ ] Confirm `FAILED`
- [ ] Add `started_at`
- [ ] Add `completed_at`
- [ ] Create migration `004_research_lifecycle.py`
- [ ] Run `alembic upgrade head`
- [ ] Run `alembic current`
- [ ] Run `alembic check`

## Pydantic Schemas

- [ ] `ResearchCreate`
- [ ] `ResearchRead`
- [ ] `ResearchComplete`
- [ ] `ResearchFail`
- [ ] `ResearchSourceCreate`
- [ ] `ResearchSourceRead`

## Service Layer

- [ ] `create_research_run`
- [ ] `list_research_for_lead`
- [ ] `get_research`
- [ ] `start_research`
- [ ] `add_research_source`
- [ ] `complete_research`
- [ ] `mark_research_partial`
- [ ] `fail_research`
- [ ] status transition validation

## Routes

- [ ] `POST /api/leads/{lead_id}/research`
- [ ] `GET /api/leads/{lead_id}/research`
- [ ] `GET /api/research/{research_id}`
- [ ] `POST /api/research/{research_id}/sources`
- [ ] `PATCH /api/research/{research_id}/start`
- [ ] `PATCH /api/research/{research_id}/complete`
- [ ] `PATCH /api/research/{research_id}/partial`
- [ ] `PATCH /api/research/{research_id}/fail`

## Event Logging

- [ ] `research_requested`
- [ ] `research_started`
- [ ] `research_source_added`
- [ ] `research_completed`
- [ ] `research_partial`
- [ ] `research_failed`

## Validation Tests

- [ ] Cannot research nonexistent lead
- [ ] Lead moves from `DISCOVERED` to `RESEARCHING`
- [ ] New research run starts as `PENDING`
- [ ] Cannot start research twice
- [ ] Can add multiple sources
- [ ] Sources link to correct research run
- [ ] Cannot complete `PENDING` research directly
- [ ] Cannot complete already completed research
- [ ] Cannot fail completed research
- [ ] Confidence rejects values below 0
- [ ] Confidence rejects values above 100
- [ ] Multiple historical research runs can exist
- [ ] Completing research does not mark lead `QUALIFIED`
- [ ] Research events are written correctly

---

# 23. Research API Definition of Done

The Research API is considered complete for MVP1 when:

```text
Research lifecycle works end-to-end
        ✓

Research history is preserved
        ✓

Multiple evidence sources are supported
        ✓

Invalid transitions are blocked
        ✓

Research event logging works
        ✓

AI/model metadata is stored
        ✓

Research completion is separate from qualification
        ✓

API tests pass
        ✓

n8n can consume the API without knowing the DB schema
        ✓
```

---

# 24. What Comes After Research API

After the Research API is stable:

```text
Research API
    ↓
Scoring API
    ↓
Product Matching
    ↓
Marketing Actions
    ↓
Approval API
    ↓
n8n Integration
    ↓
Marketing Dashboard
```

The Research API is therefore the foundation for the next intelligence stages of the platform.
