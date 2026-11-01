> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Marketing API — Approval API Status

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**API Module:** Approval API  
**Status:** COMPLETE  
**Validation Result:** PASSED  
**Current Alembic Head:** `006`  
**Next Migration ID (when actually needed):** `007`  
**Next Stage:** n8n Integration  

---

# 1. Completion Status

The MVP1 Approval API is implemented and validated.

```text
Approval API
├── Submit Marketing Action for approval       ✓
├── ApprovalRequest creation                   ✓
├── Immutable content snapshot                 ✓
├── Approval detail                            ✓
├── Approval listing                           ✓
├── Action approval history                    ✓
├── Approve flow                               ✓
├── Reject flow                                ✓
├── Request Changes flow                       ✓
├── Resubmission flow                          ✓
├── One-PENDING invariant                      ✓
├── Reviewer validation                        ✓
├── Reviewer notes validation                  ✓
├── MarketingAction synchronization            ✓
├── Event logging                              ✓
├── Lead safety                                ✓
├── ProductMatch safety                        ✓
├── Automated validation                       ✓
└── MVP1 Approval API                          COMPLETE
```

---

# 2. Architecture Preserved

The required architecture remains:

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

Rules preserved:

```text
n8n       ✕ PostgreSQL
Dashboard ✕ PostgreSQL
Internet  ✕ PostgreSQL

Marketing API ✓ PostgreSQL
```

n8n integration has NOT yet been implemented.

---

# 3. Current MVP1 Progress

```text
Companies            ✓
Contacts             ✓
Leads                ✓
Research             ✓
Scoring              ✓
Product Matching     ✓
Marketing Actions    ✓
Approval API         ✓
    ↓
n8n Integration      NEXT
```

---

# 4. Current Alembic State

Current head:

```text
006
```

Migration chain:

```text
001  initial schema
002  initial catalog
003  lead / ICP integrity
004  conceptual Research lifecycle
     actual revision: d62d40479f83
005  Marketing Actions constraints
006  Approval Request integrity
```

Migration `006` was applied successfully.

`alembic current`:

```text
006 (head)
```

`alembic check`:

```text
No new upgrade operations detected.
```

Future migration IDs must continue explicitly:

```text
007
008
009
...
```

Do not create empty migrations.

---

# 5. Migration 006

Migration:

```text
006_approval_request_integrity.py
```

Added database constraint:

```text
ck_approval_requests_status
```

Allowed ApprovalRequest statuses:

```text
PENDING
APPROVED
REJECTED
CHANGES_REQUESTED
```

Added indexes:

```text
idx_approval_requests_action
idx_approval_requests_requested_at
idx_approval_requests_status
```

Added partial unique index:

```text
idx_approval_requests_one_pending
```

Equivalent rule:

```sql
UNIQUE (marketing_action_id)
WHERE status = 'PENDING'
```

This guarantees:

```text
Maximum one active PENDING ApprovalRequest
per MarketingAction
```

---

# 6. Existing ApprovalRequest Model

Table:

```text
approval_requests
```

Fields:

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

Foreign key:

```text
marketing_action_id
→ marketing_actions.id
ON DELETE CASCADE
```

Default status:

```text
PENDING
```

---

# 7. Implemented Files

Added:

```text
api/app/schemas/approval.py
api/app/services/approval_service.py
api/app/routers/approvals.py
api/scripts/validate_approval_api.py
```

Updated:

```text
api/app/models/marketing.py
api/app/services/marketing_action_service.py
api/app/main.py
```

Migration added:

```text
database/migrations/versions/006_approval_request_integrity.py
```

---

# 8. Implemented Routes

```text
POST  /api/actions/{action_id}/submit

GET   /api/approvals
GET   /api/approvals/{approval_id}
GET   /api/actions/{action_id}/approvals

PATCH /api/approvals/{approval_id}/approve
PATCH /api/approvals/{approval_id}/reject
PATCH /api/approvals/{approval_id}/request-changes
```

OpenAPI validation confirmed all routes are registered.

---

# 9. Approval Lifecycle

ApprovalRequest lifecycle:

```text
PENDING
   ├──→ APPROVED
   ├──→ REJECTED
   └──→ CHANGES_REQUESTED
```

Terminal ApprovalRequest states:

```text
APPROVED
REJECTED
CHANGES_REQUESTED
```

ApprovalRequests are historical.

A decided ApprovalRequest is never reopened.

If changes are requested and the Marketing Action is edited:

```text
new submission
→ NEW ApprovalRequest
```

---

# 10. MarketingAction / Approval Synchronization

## Submit

```text
MarketingAction:
DRAFT → PENDING_APPROVAL

ApprovalRequest:
NEW → PENDING
```

## Approve

```text
ApprovalRequest:
PENDING → APPROVED

MarketingAction:
PENDING_APPROVAL → APPROVED
```

## Reject

```text
ApprovalRequest:
PENDING → REJECTED

MarketingAction:
PENDING_APPROVAL → REJECTED
```

## Request Changes

```text
ApprovalRequest:
PENDING → CHANGES_REQUESTED

MarketingAction:
PENDING_APPROVAL → DRAFT
```

This allows the action to be edited and resubmitted.

---

# 11. Submit-for-Approval Rules

Target:

```text
POST /api/actions/{action_id}/submit
```

Requirements:

```text
MarketingAction exists
MarketingAction.status = DRAFT
MarketingAction content is valid
lead still exists
lead remains non-terminal
lead.current_score exists
at least one ProductMatch exists
contact rules still valid
channel/action pair still valid
EMAIL requirements still valid
scheduled_at still valid if present
no active PENDING ApprovalRequest exists
```

Submission transaction:

```text
lock MarketingAction
validate current eligibility
check active PENDING approval
create content snapshot
create ApprovalRequest
update MarketingAction → PENDING_APPROVAL
write events
commit atomically
```

Response:

```text
HTTP 201
```

---

# 12. Content Snapshot

Snapshot is captured at submission time.

Validated snapshot contains:

```text
marketing_action_id
lead_id
contact_id
channel
action_type
subject
content
scheduled_at
created_by
```

Example structure:

```json
{
  "marketing_action_id": "...",
  "lead_id": "...",
  "contact_id": null,
  "channel": "LINKEDIN",
  "action_type": "POST",
  "subject": null,
  "content": "Approval validator draft.",
  "scheduled_at": null,
  "created_by": "approval-api-validator"
}
```

Snapshot behavior:

```text
created at submit time
immutable afterward
preserved across decisions
preserved after action edits
preserved after resubmission
```

---

# 13. Duplicate Pending Protection

Service layer prevents duplicate submission.

Database also guarantees:

```text
one PENDING ApprovalRequest
per MarketingAction
```

Using:

```text
idx_approval_requests_one_pending
```

Validated:

```text
duplicate submit → 409
```

Database verification:

```text
no action has multiple PENDING approvals
```

---

# 14. Approval Decision Rules

All decisions require:

```text
ApprovalRequest exists
ApprovalRequest.status = PENDING
related MarketingAction exists
MarketingAction.status = PENDING_APPROVAL
```

Decision operations lock:

```text
ApprovalRequest row
MarketingAction row
```

Decision + MarketingAction status update are committed atomically.

---

# 15. Approve

Route:

```text
PATCH /api/approvals/{approval_id}/approve
```

Payload:

```json
{
  "decided_by": "validator",
  "reviewer_notes": "Approved."
}
```

Rules:

```text
decided_by required
decided_by non-blank
reviewer_notes optional
```

Transition:

```text
ApprovalRequest:
PENDING → APPROVED

MarketingAction:
PENDING_APPROVAL → APPROVED
```

Sets:

```text
decided_by
decided_at
reviewer_notes
updated_at
```

Approved action becomes non-editable.

Approved action cannot be cancelled in MVP1.

---

# 16. Reject

Route:

```text
PATCH /api/approvals/{approval_id}/reject
```

Payload requires:

```text
decided_by
reviewer_notes
```

Both must be non-blank.

Transition:

```text
ApprovalRequest:
PENDING → REJECTED

MarketingAction:
PENDING_APPROVAL → REJECTED
```

Rejected action is terminal for MVP1.

---

# 17. Request Changes

Route:

```text
PATCH /api/approvals/{approval_id}/request-changes
```

Payload requires:

```text
decided_by
reviewer_notes
```

Transition:

```text
ApprovalRequest:
PENDING → CHANGES_REQUESTED

MarketingAction:
PENDING_APPROVAL → DRAFT
```

Result:

```text
action becomes editable again
```

After editing:

```text
POST /api/actions/{action_id}/submit
```

creates a new ApprovalRequest.

---

# 18. Resubmission Behavior

Validated flow:

```text
DRAFT
    ↓ submit
ApprovalRequest A = PENDING
    ↓ request changes
ApprovalRequest A = CHANGES_REQUESTED
MarketingAction = DRAFT
    ↓ edit
MarketingAction content changes
    ↓ submit
ApprovalRequest B = PENDING
```

Verified:

```text
ApprovalRequest B has a new ID
ApprovalRequest A still exists
ApprovalRequest A snapshot unchanged
ApprovalRequest B snapshot contains revised content
history contains both rows
newest approval appears first
```

---

# 19. Approval History

Route:

```text
GET /api/actions/{action_id}/approvals
```

Returns approval history:

```text
newest first
```

Approval history is preserved permanently unless the related MarketingAction itself is deleted and cascade behavior applies.

Validated action history contained:

```text
old CHANGES_REQUESTED approval
new PENDING / APPROVED approval
```

---

# 20. Approval Listing

Route:

```text
GET /api/approvals
```

Optional filter:

```text
status
```

Example:

```text
GET /api/approvals?status=PENDING
```

Allowed filter values:

```text
PENDING
APPROVED
REJECTED
CHANGES_REQUESTED
```

Invalid status filter:

```text
422
```

---

# 21. Marketing Action Edit / Cancellation Safety

After Approval integration, Marketing Action cancellation was tightened.

Current cancellable status:

```text
DRAFT only
```

Rejected:

```text
PENDING_APPROVAL → CANCELLED
APPROVED → CANCELLED
REJECTED → CANCELLED
CANCELLED → CANCELLED
```

Existing edit rule remains:

```text
only DRAFT actions can be edited
```

This guarantees:

```text
PENDING_APPROVAL actions cannot change
APPROVED actions cannot change
```

which protects the approval snapshot.

---

# 22. Event Logging

Approval events:

```text
approval_requested
approval_approved
approval_rejected
approval_changes_requested
```

Entity:

```text
entity_type = APPROVAL
entity_id   = ApprovalRequest.id
```

Marketing Action submission event:

```text
marketing_action_submitted
```

Entity:

```text
entity_type = MARKETING_ACTION
entity_id   = MarketingAction.id
```

Approval requested event metadata includes:

```text
approval_id
marketing_action_id
lead_id
channel
action_type
approval_status
marketing_action_status
```

Decision events include:

```text
approval_id
marketing_action_id
lead_id
decided_by
previous_approval_status
approval_status
previous_marketing_action_status
marketing_action_status
```

Event references were validated successfully.

---

# 23. Reviewer Rules

Reviewer identity uses:

```text
decided_by
```

MVP1 uses a non-empty string rather than a full user/RBAC system.

Validated:

```text
blank decided_by → 422
```

Reviewer notes:

```text
APPROVE
optional

REJECT
required

REQUEST_CHANGES
required
```

Blank required notes:

```text
422
```

---

# 24. Error Mapping

Validated behavior:

```text
unknown Marketing Action submit
→ 404

unknown ApprovalRequest
→ 404

submit non-DRAFT action
→ 409

duplicate submission
→ 409

decision on non-PENDING ApprovalRequest
→ 409

MarketingAction not PENDING_APPROVAL
→ 409

blank decided_by
→ 422

reject without notes
→ 422

reject blank notes
→ 422

request changes without notes
→ 422

request changes blank notes
→ 422

invalid approval status filter
→ 422
```

---

# 25. Cross-Module Safety

Approval API must not modify:

```text
lead.status
lead.current_score
lead_scores
product_matches
research
contacts
```

Validated:

```text
lead.status unchanged
lead.current_score unchanged
ProductMatch rows unchanged
```

Approval API owns only:

```text
ApprovalRequest
MarketingAction approval-related status
Approval events
```

---

# 26. Automated Validation

Validator:

```text
api/scripts/validate_approval_api.py
```

Final result:

```text
PASS: 143
FAIL: 0
SKIP: 0

RESULT: PASSED
```

This was a fully clean validation run.

---

# 27. Validation Actions

Created Marketing Actions:

```text
0fe63efa-62ff-4194-aa80-7c34adb7f5b8
751106ce-dd9d-4f36-af12-3cb9b925dead
0691626e-3be4-42ea-911c-2cb6e9c56d7c
```

Flows:

```text
Action 1
→ submit
→ approve

Action 2
→ submit
→ reject

Action 3
→ submit
→ request changes
→ edit
→ resubmit
→ approve
```

---

# 28. Validation ApprovalRequests

Created ApprovalRequests:

```text
8dfd2b2d-b0e4-40dc-8acf-cb4a186d354c
91829865-97d3-4f6e-a2bb-b879f1ce1fdf
dcb56c8c-8a69-4591-b053-cc433ab0df65
1c54e7b9-037b-4fe2-9866-a47f28fd3e26
```

Final states:

```text
8dfd2b2d-b0e4-40dc-8acf-cb4a186d354c
→ APPROVED

91829865-97d3-4f6e-a2bb-b879f1ce1fdf
→ REJECTED

dcb56c8c-8a69-4591-b053-cc433ab0df65
→ CHANGES_REQUESTED

1c54e7b9-037b-4fe2-9866-a47f28fd3e26
→ APPROVED
```

Validator left:

```text
0 PENDING validation approvals
```

---

# 29. Validation Coverage

Validated:

```text
OpenAPI reachable                                  ✓
Approval routes registered                         ✓
Alembic head = 006                                 ✓
approval_requests columns                          ✓
status default = PENDING                           ✓
approval status constraint                         ✓
approval indexes                                   ✓
one-PENDING partial unique index                    ✓

eligible lead                                      ✓
lead.current_score prerequisite                    ✓
ProductMatch prerequisite                          ✓

unknown action submit → 404                        ✓
unknown approval detail → 404                      ✓
unknown approve/reject/request-changes → 404       ✓
invalid status filter → 422                        ✓

draft action creation                              ✓
submit succeeds                                    ✓
ApprovalRequest created                            ✓
Approval status = PENDING                          ✓
MarketingAction = PENDING_APPROVAL                 ✓
snapshot exact                                     ✓
requested_at present                               ✓

duplicate submit rejected                          ✓
pending action non-editable                        ✓
pending action non-cancellable                     ✓

approval detail                                    ✓
pending approval list                              ✓
pending filter                                     ✓

blank reviewer identity rejected                   ✓
reject note requirements                           ✓
request-changes note requirements                  ✓

approve flow                                       ✓
reject flow                                        ✓
request-changes flow                               ✓

APPROVED action non-editable                       ✓
APPROVED action non-cancellable                    ✓

request changes returns action to DRAFT            ✓
DRAFT editable after changes                       ✓
resubmission succeeds                              ✓
new ApprovalRequest created                        ✓
old ApprovalRequest preserved                      ✓
old snapshot immutable                             ✓
new snapshot reflects edited content               ✓
approval history preserved                         ✓
approval history newest first                      ✓

lead status unchanged                              ✓
lead score unchanged                               ✓
ProductMatch unchanged                             ✓

ApprovalRequest rows persisted                     ✓
no created approval left PENDING                   ✓
no duplicate PENDING approvals                     ✓

approval_requested events                          ✓
approval_approved events                           ✓
approval_rejected events                           ✓
approval_changes_requested events                  ✓
marketing_action_submitted events                  ✓
event approval references correct                  ✓
```

---

# 30. Confirmed Approval Invariants

```text
Only DRAFT actions can be submitted                ✓
Submission creates ApprovalRequest                 ✓
ApprovalRequest starts PENDING                     ✓
One PENDING request per action                     ✓
Snapshot captured at submission                    ✓
Snapshot immutable                                 ✓

Only PENDING approvals can be decided              ✓
Approve synchronizes action                        ✓
Reject synchronizes action                         ✓
Request Changes synchronizes action                ✓

Request Changes returns action to DRAFT            ✓
Resubmission creates new approval                   ✓
Old approval history preserved                     ✓

PENDING action cannot be edited                    ✓
PENDING action cannot be cancelled                 ✓
APPROVED action cannot be edited                   ✓
APPROVED action cannot be cancelled                ✓

Reviewer identity preserved                        ✓
Decision timestamp preserved                       ✓
Reviewer notes preserved                           ✓

Lead unchanged                                     ✓
Score unchanged                                    ✓
ProductMatch unchanged                             ✓

Events written                                     ✓
DB hard constraints active                         ✓
```

---

# 31. MVP1 Definition of Done

Approval API MVP1 is complete.

```text
Submit-for-approval works                          ✓
Content snapshot works                             ✓
One-PENDING invariant enforced                     ✓
Approval detail/list/history works                 ✓
Approve works                                      ✓
Reject works                                       ✓
Request Changes works                              ✓
Resubmission works                                 ✓
Approval history preserved                         ✓
Reviewer metadata works                            ✓
Status synchronization works                       ✓
Events work                                        ✓
Lead safety works                                  ✓
Score safety works                                 ✓
ProductMatch safety works                          ✓
Automated validation passes                        ✓
```

Final:

```text
PASS: 143
FAIL: 0
SKIP: 0
RESULT: PASSED
```

---

# 32. Next Stage

Next stage:

```text
n8n Integration
```

The business API layer is now complete through human approval.

Expected high-level flow:

```text
Company / Lead Discovery
        ↓
Research
        ↓
Scoring
        ↓
Product Matching
        ↓
Marketing Action Draft
        ↓
Approval
        ↓
APPROVED
        ↓
n8n orchestration / execution
```

Do not allow n8n direct PostgreSQL access.

n8n must communicate through:

```text
HTTP / JSON
        ↓
Marketing API
```

---

# 33. Do Not Rebuild

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
Approval API

migrations 001–006
existing validation scripts
```

---

# 34. Current Final State

```text
Companies            ✓ COMPLETE
Contacts             ✓ COMPLETE
Leads                ✓ COMPLETE
Research             ✓ COMPLETE
Scoring              ✓ COMPLETE
Product Matching     ✓ COMPLETE
Marketing Actions    ✓ COMPLETE
Approval API         ✓ COMPLETE

n8n Integration      NEXT
```

Current Alembic head:

```text
006
```

Next real migration ID if genuinely needed:

```text
007
```

Approval API final result:

```text
PASS: 143
FAIL: 0
SKIP: 0
RESULT: PASSED
```

Proceed next to:

```text
n8n Integration
```
