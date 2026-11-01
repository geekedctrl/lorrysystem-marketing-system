---
title: LorrySystem Marketing Actions API — Completion Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
status: complete
current_alembic_head: "005"
next_stage: Approval API
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Marketing Actions API — Handoff

## 1. Purpose

This file is the authoritative continuation handoff for the completed **Marketing Actions API**.

Current MVP1 progress:

```text
Companies            ✓
Contacts             ✓
Leads                ✓
Research             ✓
Scoring              ✓
Product Matching     ✓
Marketing Actions    ✓ COMPLETE
Approval API         NEXT
n8n Integration      TODO
```

Do not rebuild completed modules unless a verified bug requires it.

Do not integrate n8n yet.

---

# 2. Architecture — MUST PRESERVE

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

The Marketing API owns:

```text
validation
business rules
lead lifecycle
research lifecycle
scoring
product matching
marketing action lifecycle
approval logic
event logging
database access
```

PostgreSQL owns:

```text
persistent storage
hard integrity constraints
```

n8n remains orchestration only.

---

# 3. Current Alembic State

Current head:

```text
005
```

Migration chain:

```text
001  initial schema
002  initial catalog
003  lead / ICP integrity
004  conceptual Research lifecycle
     actual revision: d62d40479f83
005  Marketing Actions constraints
```

Migration `005`:

```text
005_marketing_actions_constraints.py
```

Applied successfully:

```text
d62d40479f83 -> 005
```

`alembic current`:

```text
005 (head)
```

`alembic check`:

```text
No new upgrade operations detected.
```

Future migrations must continue explicitly:

```text
006
007
008
...
```

Do not generate random Alembic revision IDs.

---

# 4. Migration 005 Constraints

Migration `005` added:

```text
ck_marketing_actions_channel
ck_marketing_actions_action_type
ck_marketing_actions_status
ck_marketing_actions_channel_action_pair
```

Allowed channels:

```text
EMAIL
LINKEDIN
FACEBOOK
INSTAGRAM
X
```

Allowed action types:

```text
EMAIL
FOLLOW_UP
POST
COMMENT
DIRECT_MESSAGE
```

Allowed statuses:

```text
DRAFT
PENDING_APPROVAL
APPROVED
QUEUED
SENT
PUBLISHED
REJECTED
FAILED
CANCELLED
```

Allowed channel/action pairs:

```text
EMAIL
├── EMAIL
└── FOLLOW_UP

LINKEDIN
├── POST
├── COMMENT
└── DIRECT_MESSAGE

FACEBOOK
└── POST

INSTAGRAM
└── POST

X
└── POST
```

---

# 5. Existing MarketingAction Model

Current table:

```text
marketing_actions
```

Fields:

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

Foreign keys:

```text
lead_id
→ leads.id
ON DELETE SET NULL

contact_id
→ contacts.id
ON DELETE SET NULL
```

Indexes:

```text
marketing_actions_pkey
idx_marketing_actions_lead
idx_marketing_actions_status
```

---

# 6. Implemented Files

Added:

```text
api/app/schemas/marketing_action.py
api/app/services/marketing_action_service.py
api/app/routers/marketing_actions.py
api/scripts/validate_marketing_actions_api.py
```

Updated:

```text
api/app/models/marketing.py
api/app/main.py
```

Migration added:

```text
database/migrations/versions/005_marketing_actions_constraints.py
```

---

# 7. Implemented Routes

```text
POST  /api/leads/{lead_id}/actions
GET   /api/leads/{lead_id}/actions

GET   /api/actions/{action_id}
PATCH /api/actions/{action_id}

PATCH /api/actions/{action_id}/cancel
```

Not implemented yet:

```text
POST  /api/actions/{action_id}/submit
PATCH /api/actions/{action_id}/approve
PATCH /api/actions/{action_id}/reject
PATCH /api/actions/{action_id}/queue
PATCH /api/actions/{action_id}/sent
PATCH /api/actions/{action_id}/published
PATCH /api/actions/{action_id}/failed
```

Approval decisions belong to the Approval API.

Execution belongs to a later stage.

---

# 8. Marketing Action MVP1 Scope

Marketing Actions MVP1 manages:

```text
draft creation
draft retrieval
draft listing
draft editing
cancellation
lead validation
contact validation
channel validation
action-type validation
channel/action compatibility
scheduling validation
event logging
```

Marketing Actions MVP1 does NOT:

```text
send email
publish social posts
queue external workers
call provider APIs
manage provider credentials
make approval decisions
integrate n8n
```

---

# 9. Lead Eligibility Rules

Creating a Marketing Action requires:

```text
lead exists
lead is non-terminal
lead.current_score exists
at least one ProductMatch exists
```

Terminal lead statuses:

```text
CONVERTED
DISQUALIFIED
LOST
```

Marketing Action creation/editing must not modify:

```text
lead.status
lead.current_score
```

Validation confirmed both remain unchanged.

---

# 10. Product Matching Prerequisite

Required flow:

```text
Research
    ↓
Scoring
    ↓
Product Matching
    ↓
Marketing Actions
```

A Marketing Action cannot be created unless the lead has at least one existing:

```text
ProductMatch
```

Marketing Actions must not:

```text
create ProductMatches
update ProductMatches
change fit_score
```

Automated validation confirmed ProductMatch rows remain unchanged.

---

# 11. Contact Rules

For:

```text
EMAIL
FOLLOW_UP
```

requirements:

```text
contact_id required
contact must exist
contact must belong to lead.company_id
contact.email must exist
subject required
```

For:

```text
LINKEDIN + DIRECT_MESSAGE
```

requirements:

```text
contact_id required
contact must exist
contact must belong to lead.company_id
```

For general POST actions:

```text
contact_id optional
```

Validated example:

```text
LINKEDIN + POST
contact_id = NULL
→ accepted
```

---

# 12. Draft Creation Rules

Target:

```text
POST /api/leads/{lead_id}/actions
```

Required:

```text
channel
action_type
content
```

Conditional:

```text
contact_id
subject
scheduled_at
created_by
```

Rules:

```text
content must be non-empty
content must be non-blank
EMAIL requires subject
EMAIL requires contact_id
EMAIL requires contact.email
scheduled_at must be timezone-aware
scheduled_at must be in the future
```

New action status:

```text
DRAFT
```

HTTP status:

```text
201
```

---

# 13. Draft Editing Rules

Target:

```text
PATCH /api/actions/{action_id}
```

Editable fields:

```text
subject
content
contact_id
scheduled_at
```

Only actions with:

```text
status = DRAFT
```

may be edited.

Preserved:

```text
id
lead_id
channel
action_type
created_at
created_by
```

Update behavior:

```text
updated_at advances
```

Empty update:

```text
422
```

Null content:

```text
422
```

Clearing EMAIL subject:

```text
422
```

Unknown replacement contact:

```text
404
```

---

# 14. Cancellation Rules

Target:

```text
PATCH /api/actions/{action_id}/cancel
```

Cancellable statuses:

```text
DRAFT
PENDING_APPROVAL
APPROVED
```

Transition:

```text
allowed status
    ↓
CANCELLED
```

Rejected:

```text
CANCELLED → CANCELLED
SENT → CANCELLED
PUBLISHED → CANCELLED
```

Current validated path:

```text
DRAFT → CANCELLED
```

Editing a cancelled action:

```text
409
```

Cancelling an already cancelled action:

```text
409
```

---

# 15. Event Logging

Implemented events:

```text
marketing_action_created
marketing_action_updated
marketing_action_cancelled
```

Entity:

```text
entity_type = MARKETING_ACTION
entity_id   = MarketingAction.id
```

Created-event metadata includes:

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

Updated-event metadata also includes:

```text
changed_fields
```

Cancelled-event metadata includes:

```text
previous_status
status = CANCELLED
```

Event references were validated successfully.

---

# 16. API Error Mapping

Expected business errors:

```text
unknown lead
→ 404

unknown contact
→ 404

unknown Marketing Action
→ 404

contact from wrong company
→ 409

lead not eligible
→ 409

action transition not allowed
→ 409

invalid channel/action pair
→ 422

invalid draft input
→ 422
```

Pydantic validation also returns:

```text
422
```

for unsupported literal values and invalid timestamps.

---

# 17. Automated Validation

Validator:

```text
api/scripts/validate_marketing_actions_api.py
```

Final result:

```text
PASS: 92
FAIL: 0
SKIP: 4

RESULT: PASSED
```

Created validation actions:

```text
ac9cedbf-fbc5-4025-acf7-2bcc60c4f42b
6b222166-bb1d-495e-9deb-98647f8bfba7
```

Both finished as:

```text
CANCELLED
```

No active validation drafts were intentionally left behind.

---

# 18. Positive Validation Covered

Validated:

```text
OpenAPI reachable                                ✓
routes registered                                ✓
Alembic head = 005                               ✓
marketing_actions columns                        ✓
DB default status = DRAFT                        ✓
DB constraints                                   ✓
DB indexes                                       ✓

eligible lead selected                           ✓
lead.current_score exists                        ✓
lead is non-terminal                             ✓
ProductMatch prerequisite                        ✓
primary email contact selected                   ✓

valid EMAIL draft creation                       ✓
status = DRAFT                                   ✓
lead_id correct                                  ✓
contact_id correct                               ✓
channel/type correct                             ✓

action detail retrieval                          ✓
DRAFT update                                     ✓
same action ID after update                      ✓
created_at preserved                             ✓
updated_at advances                              ✓
subject updated                                  ✓
content updated                                  ✓

LINKEDIN POST without contact                     ✓
lead action list                                 ✓
newest-first ordering                            ✓

DRAFT cancellation                               ✓
status = CANCELLED                               ✓
same action ID after cancellation                ✓

lead status unchanged                            ✓
lead current_score unchanged                     ✓
ProductMatch rows unchanged                      ✓

Marketing Action DB rows persisted               ✓
validation rows finish CANCELLED                 ✓

created events                                   ✓
updated events                                   ✓
cancelled events                                 ✓
event action references                          ✓
event lead references                            ✓
```

---

# 19. Negative Validation Covered

Validated:

```text
unknown Marketing Action detail → 404             ✓
unknown Marketing Action update → 404             ✓
unknown Marketing Action cancel → 404             ✓
unknown lead → 404                                ✓
unknown contact → 404                             ✓

unsupported channel → 422                         ✓
unsupported action_type → 422                     ✓
invalid EMAIL + COMMENT → 422                     ✓

empty content → 422                               ✓
blank content → 422                               ✓
EMAIL without subject → 422                       ✓
EMAIL blank subject → 422                         ✓
EMAIL without contact → 422                       ✓

past scheduled_at → 422                           ✓
timezone-naive scheduled_at → 422                 ✓

empty update → 422                                ✓
null content update → 422                         ✓
clear EMAIL subject → 422                         ✓
unknown contact on update → 404                   ✓

edit CANCELLED action → 409                       ✓
cancel CANCELLED action → 409                     ✓
```

---

# 20. Expected Validation Skips

Four checks were skipped because matching fixtures were not available:

```text
Lead without current score -> 409
Lead without ProductMatch -> 409
Terminal lead rejected
Contact from different company -> 409
```

Validator flags:

```text
--no-score-lead-id <uuid>
--no-match-lead-id <uuid>
--terminal-lead-id <uuid>
--foreign-contact-id <uuid>
```

These are expected environment-dependent skips.

They are not implementation failures.

---

# 21. Current Validation Lead

Lead:

```text
dcb7d435-cf8c-4202-868f-3666dc53f8ac
```

Current state during validation:

```text
status = RESEARCHING
current_score = 87
```

Company:

```text
0922b777-6d1f-44ef-a675-baf1ae5b4d22
```

Primary contact:

```text
a3d990f6-13ed-4638-8262-7d523021702d
```

Contact email used:

```text
john@testlogistics.example
```

Existing ProductMatch:

```text
f5d9d060-f663-4cd3-a5ab-58934fc388df
```

Product:

```text
AI_DASHCAM
```

ProductMatch fit score:

```text
94
```

Marketing Actions validation confirmed this ProductMatch was not modified.

---

# 22. Confirmed Invariants

```text
Marketing Actions require scored lead             ✓
Marketing Actions require ProductMatch             ✓
terminal lead protection exists                    ✓
channel values controlled                          ✓
action_type values controlled                      ✓
channel/action combinations controlled             ✓
status values controlled                           ✓
EMAIL requires contact                             ✓
EMAIL requires contact email                       ✓
EMAIL requires subject                             ✓
content required                                   ✓
future scheduling enforced                         ✓

new action starts DRAFT                            ✓
only DRAFT editable                                ✓
cancellation lifecycle enforced                    ✓

lead.status unchanged                              ✓
lead.current_score unchanged                       ✓
ProductMatch unchanged                             ✓

events written                                     ✓
PostgreSQL integrity constraints active            ✓
n8n remains isolated                               ✓
```

---

# 23. Approval Boundary

Approval remains a separate module.

Marketing Actions currently does NOT create:

```text
ApprovalRequest
```

and does NOT perform:

```text
approve
reject
request changes
reviewer decision
approval snapshot
```

Recommended next integration:

```text
DRAFT
    ↓
POST /api/actions/{action_id}/submit
    ↓
PENDING_APPROVAL
    +
ApprovalRequest created
```

Do not implement `/submit` without the real Approval API persistence.

---

# 24. Existing ApprovalRequest Model

The existing SQLAlchemy model already contains:

```text
id
marketing_action_id
status
requested_at
decided_by
decided_at
reviewer_notes
content_snapshot
created_at
updated_at
```

Default approval status:

```text
PENDING
```

FK:

```text
marketing_action_id
→ marketing_actions.id
ON DELETE CASCADE
```

The Approval API should inspect this model and the live table before implementation.

---

# 25. Next Stage — Approval API

Immediate next stage:

```text
Approval API
```

Start with:

```text
1. Inspect ApprovalRequest SQLAlchemy model
2. Inspect approval_requests table
3. Inspect indexes and constraints
4. Run alembic current
5. Run alembic check
6. Define Approval lifecycle
7. Define snapshot rules
8. Define submit-for-approval transaction
9. Define approve/reject/request-changes behavior
10. Create migration 006 only if genuinely required
11. Build schemas
12. Build service
13. Build router
14. Integrate Marketing Action /submit
15. Add event logging
16. Validate end-to-end
```

Do not integrate n8n yet.

---

# 26. Do Not Rebuild

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
Marketing Actions API

existing validation scripts
migration 005
```

---

# 27. Current Project Status

```text
Companies            ✓ COMPLETE
Contacts             ✓ COMPLETE
Leads                ✓ COMPLETE
Research             ✓ COMPLETE
Scoring              ✓ COMPLETE
Product Matching     ✓ COMPLETE
Marketing Actions    ✓ COMPLETE
Approval API         NEXT
n8n Integration      TODO
```

Marketing Actions final result:

```text
MVP1 COMPLETE

PASS: 92
FAIL: 0
SKIP: 4
RESULT: PASSED
```

Current Alembic head:

```text
005
```

Next real migration ID, if Approval requires one:

```text
006
```

---

# 28. Continuation Instruction

This handoff is authoritative for the completed Marketing Actions API.

Existing source files remain authoritative for exact implementation details.

If future work requires modifying an existing file and this handoff does not contain enough implementation detail, inspect the current live source before editing it.

Immediate next task:

```text
Build and validate the Approval API.
```

Preserve:

```text
API-only DB access
Marketing API ownership of business logic
event logging
lead safety
ProductMatch safety
Marketing Action lifecycle integrity
human approval boundary
n8n isolation
```
