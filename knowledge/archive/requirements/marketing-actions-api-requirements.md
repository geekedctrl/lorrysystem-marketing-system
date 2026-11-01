---
title: LorrySystem Marketing Actions API — Requirements Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
date: 2026-09-19
status: next-build
authoritative_next_stage: Marketing Actions API
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Marketing Actions API — Requirements Handoff

## 1. Purpose

This handoff is the continuation point for building the **Marketing Actions API**.

Current MVP1 progress:

```text
Companies            ✓
Contacts             ✓
Leads                ✓
Research             ✓
Scoring              ✓
Product Matching     ✓
Marketing Actions    NEXT
Approvals             TODO
n8n Integration       TODO
```

Do not rebuild completed components unless a verified issue requires it.

---

# 2. Architecture Rules — MUST PRESERVE

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
├── business rules
├── lifecycle transitions
├── scoring logic
├── product matching
├── marketing action lifecycle
├── approval logic
├── event logging
└── database access

PostgreSQL
└── persistent storage + hard integrity constraints

n8n
└── automation / orchestration only
```

Do not integrate n8n yet.

---

# 3. Current Alembic State

Current Alembic head:

```text
d62d40479f83
```

The Research lifecycle revision is treated conceptually as migration `004`.

Future migrations must use explicit sequential IDs:

```text
005
006
007
...
```

Rules:

```text
Do not create an empty migration.
Do not modify already-applied migrations.
Only create migration 005 if Marketing Actions requires a real schema change.
Inspect the migration before applying it.
```

---

# 4. Product Matching Context

Product Matching is complete and validated.

Current Product Matching rules:

```text
one ProductMatch row per lead_id + product_id
same pair updates same row
lead must be non-terminal
lead.current_score must exist
product must exist and be active
fit_score must be 0–100
rationale must be non-blank
```

Product Matching does not change:

```text
lead.status
lead.current_score
```

Marketing Actions must preserve this separation.

---

# 5. Marketing Actions API Goal

The Marketing Actions API manages outbound marketing content/actions before execution.

Examples:

```text
EMAIL
FOLLOW_UP
LINKEDIN COMMENT
LINKEDIN POST
FACEBOOK POST
INSTAGRAM POST
X POST
DIRECT MESSAGE
```

The API should manage:

```text
draft creation
draft retrieval
draft editing
lead/contact validation
channel/action validation
action lifecycle
scheduling metadata
execution metadata
event logging
handoff to approval
```

The API should not directly send emails or publish content in the first MVP1 implementation.

---

# 6. Existing MarketingAction Model — INSPECT FIRST

The original project schema expected fields similar to:

```text
id
lead_id
contact_id
channel
action_type
subject
content
status
scheduled_at
executed_at
external_reference
created_by
created_at
updated_at
```

Before writing code:

```text
1. Inspect the actual SQLAlchemy MarketingAction model.
2. Inspect the live PostgreSQL marketing_actions table.
3. Inspect indexes and constraints.
4. Run alembic check.
5. Do not infer fields that are not present.
```

Actual source code and live database schema are authoritative for exact implementation details.

---

# 7. Recommended MVP1 Action Lifecycle

Recommended statuses:

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

Meaning:

```text
DRAFT
= editable content not yet submitted

PENDING_APPROVAL
= waiting for human approval

APPROVED
= approved by human reviewer

QUEUED
= handed to future execution workflow

SENT
= email/direct message sent

PUBLISHED
= social content published

REJECTED
= approval denied

FAILED
= external execution failed

CANCELLED
= intentionally stopped
```

---

# 8. Approval Boundary

Keep Marketing Actions and Approval as separate modules.

```text
Marketing Actions API
├── create draft
├── edit draft
├── retrieve/list action
├── cancel action
├── prepare for approval
└── record action lifecycle

Approval API
├── create approval request
├── approve
├── reject
├── request changes
├── record reviewer
└── preserve approval history/snapshot
```

Do not build full approval decision logic inside Marketing Actions.

---

# 9. Recommended Lead Eligibility

Recommended MVP1 rule for creating a Marketing Action:

```text
lead exists
lead is non-terminal
lead.current_score exists
at least one ProductMatch exists
```

Terminal statuses:

```text
CONVERTED
DISQUALIFIED
LOST
```

Creating or updating a Marketing Action must not automatically change:

```text
lead.status
lead.current_score
```

Qualification / READY_FOR_OUTREACH rules remain separate unless explicitly approved.

---

# 10. Contact Rules

## EMAIL / DIRECT_MESSAGE

Recommended:

```text
contact_id required
contact exists
contact belongs to the selected lead's company
```

For email:

```text
contact.email should exist
```

## POST

A general social post may not require a contact.

## COMMENT / DIRECT_MESSAGE

May require a contact or future external target reference.

Do not over-design platform-specific target logic in MVP1.

---

# 11. Controlled Channels

Recommended values:

```text
EMAIL
LINKEDIN
FACEBOOK
INSTAGRAM
X
```

Reject unsupported arbitrary channel values.

---

# 12. Controlled Action Types

Recommended values:

```text
EMAIL
FOLLOW_UP
POST
COMMENT
DIRECT_MESSAGE
```

Examples:

```text
EMAIL + EMAIL                ✓
EMAIL + FOLLOW_UP            ✓
LINKEDIN + POST              ✓
LINKEDIN + COMMENT           ✓
LINKEDIN + DIRECT_MESSAGE    ✓
FACEBOOK + POST              ✓
INSTAGRAM + POST             ✓
X + POST                     ✓
```

Invalid examples:

```text
EMAIL + COMMENT              ✕
INSTAGRAM + EMAIL            ✕
```

Compatibility validation belongs in the service layer.

---

# 13. Draft Validation

Required draft fields should include:

```text
channel
action_type
content
```

Potential conditional fields:

```text
subject
contact_id
scheduled_at
created_by
```

Recommended validation:

```text
content must be non-empty and non-blank
subject required for EMAIL
scheduled_at must be a valid future timestamp if provided
external_reference must not be required for draft creation
```

---

# 14. Recommended API Routes

## Create Draft

```text
POST /api/leads/{lead_id}/actions
```

Behavior:

```text
validate lead
validate contact if supplied
validate current score
validate ProductMatch prerequisite
validate channel/action pair
create DRAFT
write marketing_action_created event
```

Expected status:

```text
DRAFT
```

---

## List Lead Actions

```text
GET /api/leads/{lead_id}/actions
```

Recommended order:

```text
newest first
```

---

## Get Action

```text
GET /api/actions/{action_id}
```

Behavior:

```text
exists  → 200
missing → 404
```

---

## Update Draft

```text
PATCH /api/actions/{action_id}
```

Recommended editable fields while `DRAFT`:

```text
subject
content
contact_id
scheduled_at
```

Do not allow arbitrary edits after approval without re-approval/versioning rules.

---

## Cancel Action

```text
PATCH /api/actions/{action_id}/cancel
```

Possible allowed transitions:

```text
DRAFT → CANCELLED
PENDING_APPROVAL → CANCELLED
APPROVED → CANCELLED
```

Reject:

```text
SENT → CANCELLED
PUBLISHED → CANCELLED
```

---

# 15. Submit for Approval — Integration Decision

Recommended future route:

```text
POST /api/actions/{action_id}/submit
```

Expected transition:

```text
DRAFT → PENDING_APPROVAL
```

However, Approval API is not built yet.

Do not fake approval persistence.

Preferred order:

```text
1. Complete DRAFT management in Marketing Actions.
2. Build Approval API next.
3. Integrate /submit with actual approval-request creation.
```

If `/submit` is implemented before Approval API, document exactly what it does and does not persist.

---

# 16. Routes That Belong to Approval API

Do not add these to Marketing Actions:

```text
PATCH /api/actions/{id}/approve
PATCH /api/actions/{id}/reject
```

Approval decisions belong to Approval API.

---

# 17. Future Execution Routes

These may be introduced only after lifecycle ownership is defined:

```text
PATCH /api/actions/{id}/queue
PATCH /api/actions/{id}/sent
PATCH /api/actions/{id}/published
PATCH /api/actions/{id}/failed
```

Do not implement external provider execution yet.

---

# 18. Recommended Pydantic Schemas

Create:

```text
api/app/schemas/marketing_action.py
```

Recommended schemas:

```text
MarketingActionCreate
MarketingActionUpdate
MarketingActionRead
MarketingActionListItem
MarketingActionCancel
```

Later:

```text
MarketingActionSubmit
MarketingActionExecutionResult
MarketingActionFail
```

---

# 19. Recommended Service Layer

Create:

```text
api/app/services/marketing_action_service.py
```

Responsibilities:

```text
create_action()
get_action()
list_actions_for_lead()
update_draft()
cancel_action()

validate_lead_eligibility()
validate_contact_relationship()
validate_channel_action_pair()
validate_action_transition()
```

Later:

```text
submit_for_approval()
queue_action()
mark_sent()
mark_published()
mark_failed()
```

Business logic belongs in the service layer, not routers.

---

# 20. Recommended Router

Create:

```text
api/app/routers/marketing_actions.py
```

Flow:

```text
HTTP request
    ↓
Pydantic validation
    ↓
Marketing Action service
    ↓
SQLAlchemy
    ↓
PostgreSQL
```

Keep the router thin.

---

# 21. Event Logging

Recommended events:

```text
marketing_action_created
marketing_action_updated
marketing_action_cancelled
marketing_action_submitted
marketing_action_queued
marketing_action_sent
marketing_action_published
marketing_action_failed
```

Minimum first-build events:

```text
marketing_action_created
marketing_action_updated
marketing_action_cancelled
```

Example metadata:

```json
{
  "lead_id": "...",
  "action_id": "...",
  "contact_id": "...",
  "channel": "EMAIL",
  "action_type": "EMAIL",
  "status": "DRAFT"
}
```

---

# 22. Relationship to Product Matching

Marketing Actions consume Product Matching context.

Recommended flow:

```text
Research
    ↓
Scoring
    ↓
Product Matching
    ↓
Marketing Action
```

Marketing Actions must not:

```text
create ProductMatches
update ProductMatches
change fit_score
```

If content generation needs product context, retrieve existing ProductMatch data through the application layer.

---

# 23. Lead Safety

Marketing Action creation/editing must not alter:

```text
lead.status
lead.current_score
```

Do not automatically perform:

```text
Marketing Action created
→ READY_FOR_OUTREACH
```

unless a qualification/outreach-readiness policy is explicitly approved later.

---

# 24. Database / Migration Inspection

Before coding:

```text
inspect marketing_actions table
inspect SQLAlchemy model
inspect indexes
inspect constraints
run alembic current
run alembic check
```

Create migration `005` only if a real schema change is required.

Possible justified changes:

```text
status CHECK constraint
channel CHECK constraint
action_type CHECK constraint
missing indexes
nullable-rule changes
```

---

# 25. Recommended Indexes to Check

Inspect whether these already exist:

```text
lead_id
contact_id
status
channel
created_at
scheduled_at
```

Potential examples:

```sql
CREATE INDEX idx_marketing_actions_lead_id
ON marketing_actions (lead_id);

CREATE INDEX idx_marketing_actions_status
ON marketing_actions (status);

CREATE INDEX idx_marketing_actions_created_at
ON marketing_actions (created_at DESC);
```

Only add what is actually needed.

---

# 26. Validation Requirements

Automated validation should cover:

```text
OpenAPI reachable                                  ✓
Action routes registered                           ✓
marketing_actions columns correct                  ✓
DB constraints/indexes correct                     ✓

unknown lead → 404
terminal lead rejected
lead without current score rejected
lead without ProductMatch rejected

unknown contact → 404
contact from different company rejected

invalid channel rejected
invalid action type rejected
invalid channel/action pair rejected

empty content rejected
blank content rejected
email without subject rejected

valid draft creation succeeds
created status = DRAFT
action detail retrieval works
lead action list works
newest-first ordering works

draft update works
action ID preserved
created_at preserved
updated_at advances

cancel transition works
invalid transitions rejected

lead.status unchanged
lead.current_score unchanged
ProductMatch rows unchanged

events exist
event lead reference correct
event action reference correct
event channel/type correct
```

---

# 27. Validation Script

Create:

```text
api/scripts/validate_marketing_actions_api.py
```

Output format:

```text
PASS: <n>
FAIL: <n>
SKIP: <n>

RESULT: PASSED / FAILED
```

Environment-dependent checks may be skipped cleanly when required fixtures do not exist.

---

# 28. MVP1 Definition of Done

Marketing Actions API is complete when:

```text
Draft creation works                               ✓
Draft retrieval works                              ✓
Lead action list works                             ✓
Draft editing works                                ✓
Channel validation works                           ✓
Action-type validation works                       ✓
Channel/action compatibility works                 ✓
Lead/contact validation works                      ✓
Current-score prerequisite works                   ✓
ProductMatch prerequisite works                    ✓
Terminal lead protection works                     ✓
Cancellation works                                 ✓
Invalid transitions are rejected                   ✓
Event logging works                                ✓
Lead status remains unchanged                      ✓
Lead current score remains unchanged               ✓
ProductMatch data remains unchanged                ✓
Automated validation passes                        ✓
```

Approval decisions do not need to be implemented inside this module.

---

# 29. MVP1 Scope Boundary

Marketing Actions MVP1 should focus on:

```text
draft creation
draft editing
retrieval
listing
validation
cancellation
event logging
handoff to Approval API
```

Do not expand this API into:

```text
actual email sending
actual social publishing
provider credentials
retry workers
rate-limit engines
social platform connectors
email deliverability infrastructure
campaign management
```

Those belong later.

---

# 30. Recommended Build Order

```text
CURRENT STATE
    ↓
Inspect MarketingAction model
    ↓
Inspect live table/indexes/constraints
    ↓
Run alembic check
    ↓
Lock Marketing Action business rules
    ↓
Migration 005 only if required
    ↓
Pydantic schemas
    ↓
Service layer
    ↓
Router
    ↓
Lifecycle validation
    ↓
Event logging
    ↓
Automated validation
    ↓
Marketing Actions COMPLETE
    ↓
Approval API NEXT
```

---

# 31. Immediate Checklist

## Inspection

- [ ] Inspect current `MarketingAction` SQLAlchemy model
- [ ] Inspect live `marketing_actions` table
- [ ] Inspect indexes
- [ ] Inspect constraints
- [ ] Run `alembic current`
- [ ] Run `alembic check`

## Business Rules

- [ ] Confirm statuses
- [ ] Confirm channels
- [ ] Confirm action types
- [ ] Confirm channel/action compatibility
- [ ] Confirm ProductMatch prerequisite
- [ ] Confirm current-score prerequisite
- [ ] Confirm contact requirements
- [ ] Confirm draft-edit rules
- [ ] Confirm cancellation rules
- [ ] Confirm Approval API handoff

## Implementation

- [ ] Create schemas
- [ ] Create service
- [ ] Create router
- [ ] Register router
- [ ] Add event logging
- [ ] Create migration only if needed
- [ ] Create validation script

## Testing

- [ ] Positive draft creation
- [ ] Negative lead tests
- [ ] Negative contact tests
- [ ] Negative channel/action tests
- [ ] Draft update tests
- [ ] Cancellation tests
- [ ] Invalid transition tests
- [ ] Event verification
- [ ] DB invariant verification
- [ ] Lead safety verification
- [ ] ProductMatch safety verification

---

# 32. Continuation Instruction for the Next Chat

Continue from the existing implementation.

Do not recreate:

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
Scoring API
Product Matching API
existing validation scripts
```

Current Product Matching status:

```text
MVP1 COMPLETE

PASS: 58
FAIL: 0
SKIP: 2
RESULT: PASSED
```

Current Alembic head:

```text
d62d40479f83
```

Immediate next task:

```text
1. Inspect MarketingAction SQLAlchemy model.
2. Inspect live marketing_actions table.
3. Inspect indexes and constraints.
4. Run alembic check.
5. Finalize Marketing Actions business rules.
6. Create migration 005 only if genuinely required.
7. Build schemas.
8. Build service.
9. Build router.
10. Add event logging.
11. Validate end-to-end.
```

Do not integrate n8n yet.

Next authoritative build stage:

```text
Marketing Actions API
```

After completion:

```text
Approval API
```
