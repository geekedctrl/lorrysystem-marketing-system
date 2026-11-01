> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem AI Marketing & Lead Generation — MVP1 Final Architecture

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**Document Type:** Final Architecture / Completion Tracker  
**Status:** MARKETING API COMPLETE  
**Current Alembic Head:** `006`  
**Next Stage:** n8n Integration  
**Final Full-Stack Regression Result:** PASSED  

---

# 1. MVP1 Status

The Marketing API business layer is complete for MVP1.

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

The Marketing API server is now ready to act as the central business-logic layer for future n8n orchestration.

---

# 2. Final Architecture

```text
                ┌──────────────────────────┐
                │          n8n             │
                │  Automation / Workflow   │
                │       Orchestration      │
                └────────────┬─────────────┘
                             │
                             │ HTTP / JSON
                             ▼
                ┌──────────────────────────┐
                │      Marketing API       │
                │        FastAPI           │
                │                          │
                │ Business Rules           │
                │ Validation               │
                │ Lifecycle Control        │
                │ Approval Control         │
                │ Event Logging            │
                │ Database Access          │
                └────────────┬─────────────┘
                             │
                             │ SQLAlchemy / psycopg
                             ▼
                ┌──────────────────────────┐
                │       PostgreSQL         │
                │                          │
                │ Persistence              │
                │ Constraints              │
                │ Indexes                  │
                │ Audit Data               │
                └──────────────────────────┘
```

---

# 3. Architecture Rules

The following architecture boundary must remain intact:

```text
n8n       ✕ PostgreSQL
Dashboard ✕ PostgreSQL
Internet  ✕ PostgreSQL

Marketing API ✓ PostgreSQL
```

n8n must never bypass the Marketing API and connect directly to PostgreSQL.

All future automation should use:

```text
n8n
 ↓
HTTP / JSON
 ↓
Marketing API
 ↓
PostgreSQL
```

---

# 4. Responsibility Boundaries

## Marketing API owns

```text
input validation
business rules
lead lifecycle
research lifecycle
scoring lifecycle
product matching
marketing action lifecycle
approval lifecycle
event logging
database access
cross-module consistency
```

## PostgreSQL owns

```text
persistent storage
primary keys
foreign keys
unique constraints
check constraints
partial unique indexes
hard data integrity
```

## n8n will own

```text
workflow orchestration
scheduling
calling API endpoints
external-service integrations
trigger handling
automation sequencing
```

n8n must not duplicate the Marketing API's business rules.

---

# 5. Current Alembic State

Current Alembic head:

```text
006
```

Migration history:

```text
001  Initial schema
002  Initial product/catalog seed
003  Lead / ICP integrity
004  Conceptual Research lifecycle
     actual revision: d62d40479f83
005  Marketing Actions constraints
006  Approval Request integrity
```

Current state:

```text
alembic current
→ 006 (head)

alembic check
→ No new upgrade operations detected.
```

Future migrations must continue explicitly:

```text
007
008
009
...
```

Do not create empty migrations.

Do not rename already-applied migrations.

---

# 6. Companies API

Status:

```text
COMPLETE
```

Responsibilities:

```text
create companies
list companies
retrieve company
company data validation
normalized company data
```

Core routes include:

```text
POST /api/companies
GET  /api/companies
GET  /api/companies/{company_id}
```

---

# 7. Contacts API

Status:

```text
COMPLETE
```

Responsibilities:

```text
create contact
list contacts
retrieve contact
company/contact relationship
primary contact support
contact information storage
```

Core routes include:

```text
POST /api/contacts
GET  /api/contacts
GET  /api/contacts/{contact_id}
```

---

# 8. Leads API

Status:

```text
COMPLETE
```

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

Alternative terminal statuses:

```text
DISQUALIFIED
LOST
```

Important MVP1 rule:

```text
Research
Scoring
Product Matching
Marketing Actions
Approval

do NOT automatically invent qualification rules
or silently move the lead through unrelated states.
```

Qualification formula/threshold remains intentionally deferred.

---

# 9. Research API

Status:

```text
COMPLETE
```

Research lifecycle:

```text
PENDING
  ↓
RUNNING
  ├── COMPLETED
  ├── PARTIAL
  └── FAILED
```

Research table:

```text
lead_research
```

Research source table:

```text
research_sources
```

Core routes:

```text
POST  /api/leads/{lead_id}/research
GET   /api/leads/{lead_id}/research
GET   /api/research/{research_id}
PATCH /api/research/{research_id}/start
POST  /api/research/{research_id}/sources
PATCH /api/research/{research_id}/complete
PATCH /api/research/{research_id}/partial
PATCH /api/research/{research_id}/fail
```

Final original Research validator:

```text
PASS: 80
FAIL: 0
SKIP: 1
RESULT: PASSED
```

---

# 10. Scoring API

Status:

```text
COMPLETE
```

Design:

```text
lead_scores = historical scoring records
```

Each scoring operation creates a new historical row.

Exactly one row per lead is:

```text
is_current = TRUE
```

And:

```text
leads.current_score
=
current lead_scores.total_score
```

Core routes:

```text
POST /api/leads/{lead_id}/scores
GET  /api/leads/{lead_id}/scores
GET  /api/leads/{lead_id}/scores/current
GET  /api/scoring/{score_id}
```

Scoring requires usable Research:

```text
COMPLETED
or
PARTIAL
```

Scoring does not automatically qualify the lead.

Final original Scoring validator:

```text
PASS: 58
FAIL: 0
SKIP: 2
RESULT: PASSED
```

---

# 11. Product Matching API

Status:

```text
COMPLETE
```

Product Matching design:

```text
one mutable ProductMatch
per
(lead_id, product_id)
```

Unlike scores, ProductMatch is not historical.

Repeated matching updates the existing row.

Rules:

```text
lead must exist
lead must be non-terminal
lead.current_score must exist
product must exist
product must be active
fit_score must be 0..100
rationale required
```

Core routes:

```text
GET  /api/products
GET  /api/products/{product_id}
POST /api/leads/{lead_id}/product-matches
GET  /api/leads/{lead_id}/product-matches
GET  /api/product-matches/{match_id}
```

Current product catalog:

```text
TMS
GPS
AI_DASHCAM
DMS
MDVR
FUEL_MONITORING
```

Final original Product Matching validator:

```text
PASS: 58
FAIL: 0
SKIP: 2
RESULT: PASSED
```

Later deep regression run:

```text
PASS: 59
FAIL: 0
SKIP: 2
RESULT: PASSED
```

---

# 12. Marketing Actions API

Status:

```text
COMPLETE
```

Marketing Action statuses:

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

Supported channels:

```text
EMAIL
LINKEDIN
FACEBOOK
INSTAGRAM
X
```

Supported action types:

```text
EMAIL
FOLLOW_UP
POST
COMMENT
DIRECT_MESSAGE
```

Allowed channel/action pairs:

```text
EMAIL     + EMAIL
EMAIL     + FOLLOW_UP

LINKEDIN  + POST
LINKEDIN  + COMMENT
LINKEDIN  + DIRECT_MESSAGE

FACEBOOK  + POST
INSTAGRAM + POST
X         + POST
```

Core routes:

```text
POST  /api/leads/{lead_id}/actions
GET   /api/leads/{lead_id}/actions
GET   /api/actions/{action_id}
PATCH /api/actions/{action_id}
PATCH /api/actions/{action_id}/cancel
```

Edit rule:

```text
DRAFT only
```

Cancellation rule after Approval integration:

```text
DRAFT → CANCELLED
```

Not cancellable:

```text
PENDING_APPROVAL
APPROVED
REJECTED
SENT
PUBLISHED
CANCELLED
```

Final original Marketing Actions validator:

```text
PASS: 92
FAIL: 0
SKIP: 4
RESULT: PASSED
```

---

# 13. Approval API

Status:

```text
COMPLETE
```

ApprovalRequest statuses:

```text
PENDING
APPROVED
REJECTED
CHANGES_REQUESTED
```

Approval lifecycle:

```text
PENDING
   ├── APPROVED
   ├── REJECTED
   └── CHANGES_REQUESTED
```

Marketing Action synchronization:

```text
SUBMIT
DRAFT → PENDING_APPROVAL
ApprovalRequest → PENDING

APPROVE
PENDING_APPROVAL → APPROVED
ApprovalRequest → APPROVED

REJECT
PENDING_APPROVAL → REJECTED
ApprovalRequest → REJECTED

REQUEST CHANGES
PENDING_APPROVAL → DRAFT
ApprovalRequest → CHANGES_REQUESTED
```

Core routes:

```text
POST  /api/actions/{action_id}/submit

GET   /api/approvals
GET   /api/approvals/{approval_id}
GET   /api/actions/{action_id}/approvals

PATCH /api/approvals/{approval_id}/approve
PATCH /api/approvals/{approval_id}/reject
PATCH /api/approvals/{approval_id}/request-changes
```

Important Approval invariant:

```text
maximum one active PENDING ApprovalRequest
per MarketingAction
```

Database protection:

```text
idx_approval_requests_one_pending
```

Equivalent rule:

```sql
UNIQUE (marketing_action_id)
WHERE status = 'PENDING'
```

Approval content snapshot is:

```text
captured at submission
immutable
historical
preserved after action edits
preserved after resubmission
```

Final Approval validator:

```text
PASS: 143
FAIL: 0
SKIP: 0
RESULT: PASSED
```

---

# 14. Event Logging

Marketing API event logging is active.

Important Marketing Action events:

```text
marketing_action_created
marketing_action_updated
marketing_action_cancelled
marketing_action_submitted
```

Approval events:

```text
approval_requested
approval_approved
approval_rejected
approval_changes_requested
```

Events are used for:

```text
audit history
state-transition tracking
future automation observability
future n8n integration
```

---

# 15. Cross-Module Safety

The following ownership boundaries are preserved.

Research must not silently modify:

```text
scores
ProductMatches
Marketing Actions
Approvals
```

Scoring must not automatically modify:

```text
lead qualification
ProductMatches
Marketing Actions
Approvals
```

Product Matching must not modify:

```text
lead.status
lead.current_score
Research
Scores
```

Marketing Actions must not modify:

```text
lead.status
lead.current_score
ProductMatch
Research
Scores
```

Approval must not modify:

```text
lead.status
lead.current_score
lead_scores
product_matches
research
contacts
```

Approval owns only:

```text
ApprovalRequest
MarketingAction approval-related status
Approval events
```

---

# 16. Final Full-Stack Regression Validator

Master validator:

```text
api/scripts/validate_full_stack.py
```

Purpose:

```text
validate API routes
validate Alembic state
validate DB tables
validate constraints
validate indexes
validate stage-by-stage consistency
validate cross-module relationships
validate event history
run individual deep validators
```

Deep mode:

```text
--deep
```

Runs:

```text
validate_approval_api.py
validate_marketing_actions_api.py
validate_product_matching_api.py
validate_research_api.py
validate_scoring_api.py
```

---

# 17. Final Full-Stack Regression Result

Final deep regression:

```text
PASS: 109
FAIL: 0
SKIP: 0

RESULT: PASSED
```

Stage results:

```text
PRECHECK             PASSED
ROUTES               PASSED
DATABASE             PASSED
FOUNDATION           PASSED
RESEARCH             PASSED
SCORING              PASSED
PRODUCT_MATCHING     PASSED
MARKETING_ACTIONS    PASSED
APPROVAL             PASSED
CROSS_STAGE          PASSED
EVENTS               PASSED
DEEP                 PASSED
```

This confirms both:

```text
the whole system is assembled correctly
```

and:

```text
the individual business modules still behave correctly
```

---

# 18. Current Validation Lead

Primary regression lead:

```text
lead_id:
dcb7d435-cf8c-4202-868f-3666dc53f8ac
```

Current verified state:

```text
status        = RESEARCHING
priority      = HIGH
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

Current ProductMatch:

```text
f5d9d060-f663-4cd3-a5ab-58934fc388df
```

Product:

```text
AI_DASHCAM
```

Current verified fit score:

```text
94
```

---

# 19. Marketing API MVP1 Definition of Done

The Marketing API business server is considered complete because:

```text
Companies work                                      ✓
Contacts work                                       ✓
Leads work                                          ✓
Research works                                      ✓
Scoring works                                       ✓
Product Matching works                              ✓
Marketing Actions work                              ✓
Approval works                                      ✓

Database constraints active                         ✓
Migration chain clean                               ✓
Cross-module consistency verified                   ✓
Event logging verified                              ✓
Approval history verified                           ✓
Lead safety verified                                ✓
Score safety verified                               ✓
ProductMatch safety verified                        ✓

Full regression passed                              ✓
Deep validators passed                              ✓
```

---

# 20. MVP1 Business Pipeline

Current completed business pipeline:

```text
Company
  ↓
Contact
  ↓
Lead
  ↓
Research
  ↓
Scoring
  ↓
Product Matching
  ↓
Marketing Action Draft
  ↓
Human Approval
```

Future automated flow:

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

---

# 21. What Is NOT Part of the Completed Marketing API Yet

The following are intentionally outside the completed MVP1 business API layer:

```text
n8n orchestration
email sending
LinkedIn posting
Facebook posting
Instagram posting
X posting
provider integrations
campaign management
retry queues
execution workers
authentication / RBAC
complex approval chains
dashboard UI
production observability stack
```

These can be added in later stages without rebuilding the completed business API.

---

# 22. Next Stage — n8n Integration

Next stage:

```text
n8n Integration
```

Goal:

```text
n8n calls the Marketing API
instead of accessing PostgreSQL directly
```

Expected orchestration model:

```text
Trigger
   ↓
n8n
   ↓
Marketing API
   ↓
Business logic / validation
   ↓
PostgreSQL
```

n8n should orchestrate the existing API rather than reimplementing it.

---

# 23. Do Not Rebuild

The following components are complete and should not be recreated unless a verified defect requires it:

```text
PostgreSQL deployment
Docker network structure
FastAPI application foundation
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

Migrations 001–006
Existing validation scripts
Master full-stack regression validator
```

---

# 24. Final MVP1 Architecture State

```text
                    ┌─────────────────────┐
                    │      Companies      │
                    │      Contacts       │
                    │       Leads         │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │      Research       │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │       Scoring       │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │  Product Matching   │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │ Marketing Actions   │
                    └──────────┬──────────┘
                               ↓
                    ┌─────────────────────┐
                    │      Approval       │
                    └──────────┬──────────┘
                               ↓
                         API COMPLETE
                               ↓
                    ┌─────────────────────┐
                    │  n8n Integration    │
                    │        NEXT         │
                    └─────────────────────┘
```

---

# 25. Final Completion Statement

The LorrySystem Marketing API server is complete for MVP1.

Current state:

```text
Marketing API Business Layer   ✓ COMPLETE
PostgreSQL Persistence Layer   ✓ COMPLETE
Human Approval Layer           ✓ COMPLETE
Database Integrity Rules       ✓ COMPLETE
Cross-Stage Validation         ✓ COMPLETE
Regression Validation          ✓ COMPLETE

n8n Integration                NEXT
```

Final regression result:

```text
PASS: 109
FAIL: 0
SKIP: 0
RESULT: PASSED
```

Current Alembic head:

```text
006
```

Next stage:

```text
n8n Integration
```
