---
title: LorrySystem MVP1 Dashboard — Requirements & Implementation Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
date: 2026-09-19
status: ready-to-build
priority: high
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem MVP1 Dashboard — Requirements & Implementation Handoff

## 1. Purpose

This document defines how the **MVP1 Dashboard** should look, behave, and integrate with the existing LorrySystem Marketing API.

The dashboard is now an **MVP1 requirement**.

A critical requirement is:

> **Parimala must be able to manually enter leads through the dashboard.**

The dashboard should also let her review the lead pipeline, inspect AI-generated work, and perform human approvals without using Swagger, PostgreSQL, or n8n directly.

The goal is to get an operational dashboard running as quickly as possible without weakening the architecture or security model.

---

# 2. Current Project State

```text
Companies            ✓ COMPLETE
Contacts             ✓ COMPLETE
Leads                ✓ COMPLETE
Research             ✓ COMPLETE
Scoring              ✓ COMPLETE
Product Matching     ✓ COMPLETE
Marketing Actions    ✓ COMPLETE
Approval API         ✓ COMPLETE

MVP1 Security        NEXT / IN PROGRESS
n8n Integration      NEXT
MVP1 Dashboard       NOW REQUIRED
```

Current Alembic head:

```text
006
```

Do not rebuild existing APIs.

Do not give the dashboard direct PostgreSQL access.

---

# 3. Dashboard Objective

The dashboard should answer five questions quickly:

```text
1. What leads do we currently have?
2. Can I manually add a new lead?
3. What stage is each lead at?
4. What has the AI generated/recommended?
5. What requires human approval?
```

Parimala should not need technical knowledge to use it.

---

# 4. MVP1 Dashboard Scope

MVP1 should contain:

```text
Dashboard / Overview
Leads
Add Lead
Lead Details
Marketing Actions
Approval Queue
Recent Activity
Basic System Status
```

Do NOT build yet:

```text
complex analytics
campaign builder
multi-workspace management
advanced reports
enterprise RBAC
user administration
custom workflow editor
social publishing UI
full CRM features
billing
advanced settings
```

Those belong in later MVPs.

---

# 5. Fastest Recommended Architecture

The browser must **not contain the Marketing API service Bearer token**.

Recommended architecture:

```text
Parimala's Browser
        │
        │ HTTPS
        ▼
Cloudflare Access
        │
        ▼
Dashboard / BFF
        │
        │ Authorization: Bearer <dashboard-service-token>
        ▼
Marketing API
        │
        ▼
PostgreSQL
```

BFF = Backend For Frontend.

Rules:

```text
Browser        ✕ PostgreSQL
Browser        ✕ Marketing API service secret
Dashboard BFF  ✕ PostgreSQL

Dashboard BFF  ✓ Marketing API
Marketing API  ✓ PostgreSQL
```

---

# 6. Recommended Technology for MVP1

For the fastest implementation with the current Python stack:

```text
FastAPI
Jinja2
HTMX
HTML/CSS
small amount of JavaScript only where needed
```

Why:

```text
same Python ecosystem
no large frontend build required
easy Docker deployment
fast server-rendered forms
service token stays server-side
simple to maintain
```

A React/Next.js frontend can be introduced later if the dashboard grows substantially.

MVP1 should prioritize:

```text
working
secure
clean
fast
```

---

# 7. Main Layout

```text
┌─────────────────────────────────────────────────────────────┐
│ LorrySystem AI Marketing                     Parimala ▼     │
├──────────────┬──────────────────────────────────────────────┤
│              │                                              │
│ Overview     │                                              │
│ Leads        │                PAGE CONTENT                  │
│ + Add Lead   │                                              │
│ Actions      │                                              │
│ Approvals    │                                              │
│ Activity     │                                              │
│              │                                              │
│──────────────│                                              │
│ System       │                                              │
│              │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

Recommended sidebar:

```text
Overview
Leads
Add Lead
Marketing Actions
Approvals
Activity
System
```

---

# 8. Visual Style

Use a professional operations-dashboard style:

```text
clean white/light-grey main background
dark sidebar
clear typography
minimal animations
status badges
simple tables
large readable buttons
clear error messages
responsive for laptop/tablet
```

Avoid:

```text
heavy gradients
decorative graphics
over-animation
dense enterprise menus
tiny text
```

---

# 9. Overview Page

Route:

```text
/dashboard
```

Show:

```text
Active Leads
Pending Approvals
Draft Marketing Actions
Approved Actions
```

Example:

```text
┌─────────────────┐ ┌─────────────────┐
│ Active Leads    │ │ Pending Approval│
│       24        │ │        5        │
└─────────────────┘ └─────────────────┘

┌─────────────────┐ ┌─────────────────┐
│ Draft Actions   │ │ Approved Actions│
│       8         │ │        3        │
└─────────────────┘ └─────────────────┘
```

Below:

```text
Recent Leads
Pending Approval Items
Recent Activity
```

Prominent CTA:

```text
+ Add Lead
```

---

# 10. Leads Page

Route:

```text
/leads
```

Display:

| Company | ICP | Status | Priority | Score | Primary Contact | Actions |
|---|---|---|---|---:|---|---|

Recommended filters:

```text
Search
Status
ICP
Priority
```

Search should ideally match:

```text
company name
domain
contact name/email where available
```

---

# 11. Lead Status Display

Use existing lead lifecycle exactly:

```text
DISCOVERED
RESEARCHING
QUALIFIED
READY_FOR_OUTREACH
CONTACTED
REPLIED
CONVERTED
DISQUALIFIED
LOST
```

Do not invent a separate dashboard lifecycle.

---

# 12. Manual Lead Entry — Critical MVP1 Feature

Parimala clicks:

```text
+ Add Lead
```

Recommended flow:

```text
Step 1 — Company
        ↓
Step 2 — ICP
        ↓
Step 3 — Contact (optional)
        ↓
Step 4 — Lead Details
        ↓
Review
        ↓
Create Lead
```

---

# 13. Step 1 — Company

First search existing companies.

UI:

```text
Company
[ Search existing company... ]

or

[ + Create New Company ]
```

If company exists:

```text
select it
```

If not:

```text
show company creation form
```

Use fields supported by the existing Companies API.

Before implementation inspect:

```text
api/app/schemas/company.py
POST /api/companies
```

Existing duplicate protection includes:

```text
domain
normalized company name
website
```

If API returns `409`, show:

```text
A matching company already exists.
Use the existing company instead.
```

Do not expose raw JSON errors.

---

# 14. Step 2 — ICP

ICP is required.

Current profiles:

```text
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
COMMERCIAL_ENTERPRISE
```

Human labels:

```text
Logistics / Haulage
Passenger Transport
Commercial / Enterprise Fleet
```

Submit the actual existing ICP ID.

Do not hard-code database UUIDs into frontend code.

Load ICP options from the existing API/catalog layer if available.

If an ICP endpoint is missing, inspect current implementation before adding one.

---

# 15. Step 3 — Contact

Primary contact is optional.

UI may contain:

```text
Name
Job Title
Email
Phone
```

Exact fields must follow the current Contacts API schema.

Allow:

```text
Skip for now
```

If contact is created:

```text
contact.company_id
must match
lead.company_id
```

Existing duplicate-email rules remain authoritative.

---

# 16. Step 4 — Lead Details

Required:

```text
company_id
icp_profile_id
```

Optional:

```text
primary_contact_id
```

Priority:

```text
LOW
MEDIUM
HIGH
```

Recommended default:

```text
MEDIUM
```

New leads automatically start:

```text
DISCOVERED
```

The dashboard must not force another initial status.

---

# 17. Review and Create

Show:

```text
Company
ICP
Primary Contact
Priority
```

Buttons:

```text
Back
Create Lead
```

After success:

```text
Lead created successfully.
```

Redirect to:

```text
/leads/{lead_id}
```

---

# 18. Duplicate Active Lead Handling

Existing rule:

```text
one active lead per company_id + icp_profile_id
```

If creation returns `409`, show:

```text
An active lead already exists for this company and ICP.
```

If possible provide:

```text
View Existing Lead
```

Do not bypass the API rule.

---

# 19. Lead Detail Page

Route:

```text
/leads/{lead_id}
```

Header:

```text
Company Name
Lead Status
Priority
Current Score
ICP
```

Sections/tabs:

```text
Overview
Research
Scoring
Product Matches
Marketing Actions
Approvals
Activity
```

---

# 20. Lead Overview

Show:

```text
Company information
Primary contact
ICP
Current status
Priority
Current score
Created date
Last updated
```

Avoid displaying UUIDs prominently.

---

# 21. Research Section

Show research history:

```text
status
created_at
started_at
completed_at
confidence
model/provider where useful
summary/output
sources
```

Statuses:

```text
PENDING
RUNNING
COMPLETED
PARTIAL
FAILED
```

---

# 22. Scoring Section

Show:

```text
Current Score
Scoring Version
Rationale
Score Breakdown
Previous Scores
```

Example:

```text
87 / 100
```

History:

```text
newest first
```

---

# 23. Product Matches

Display:

| Product | Fit Score | Rationale |
|---|---:|---|
| AI Dashcam | 94 | ... |
| GPS | 82 | ... |

MVP1 should be read-only here unless manual ProductMatch editing is separately approved.

---

# 24. Marketing Actions

Display lead actions with:

```text
Channel
Action Type
Status
Subject
Created
Updated
```

Click to inspect full content.

---

# 25. Marketing Actions Page

Route:

```text
/actions
```

Filters:

```text
Status
Channel
Action Type
```

Table:

| Company | Channel | Type | Status | Created | Action |
|---|---|---|---|---|---|

This page is primarily for operational visibility.

---

# 26. Approval Queue — Critical MVP1 Feature

Route:

```text
/approvals
```

Default:

```text
PENDING approvals
```

Each approval should show:

```text
Company
Lead
Channel
Action Type
Subject
Content
Requested At
```

Example:

```text
┌──────────────────────────────────────────────────┐
│ Test Logistics Sdn Bhd                           │
│ EMAIL                                             │
│                                                  │
│ Subject: Improve fleet visibility                │
│                                                  │
│ Hi John,                                         │
│ ...                                              │
│                                                  │
│ [Approve] [Request Changes] [Reject]             │
└──────────────────────────────────────────────────┘
```

---

# 27. Approval Content Source

Use the immutable:

```text
content_snapshot
```

for approval review.

Do not rebuild approval content from mutable MarketingAction fields when a snapshot exists.

---

# 28. Approve Flow

Button:

```text
Approve
```

Call:

```text
PATCH /api/approvals/{approval_id}/approve
```

Expected API result:

```text
ApprovalRequest → APPROVED
MarketingAction → APPROVED
```

Refresh using current API state.

---

# 29. Reject Flow

Require reviewer notes.

Call:

```text
PATCH /api/approvals/{approval_id}/reject
```

Expected:

```text
ApprovalRequest → REJECTED
MarketingAction → REJECTED
```

---

# 30. Request Changes Flow

Require reviewer notes.

Call:

```text
PATCH /api/approvals/{approval_id}/request-changes
```

Expected:

```text
ApprovalRequest → CHANGES_REQUESTED
MarketingAction → DRAFT
```

The action becomes editable again.

---

# 31. Reviewer Identity

Do not make Parimala type her name for every decision.

Recommended MVP1 behavior:

```text
Cloudflare Access identity
        ↓
Dashboard BFF
        ↓
decided_by
```

If available, the BFF may use the verified Cloudflare authenticated email as `decided_by`.

Do not trust an arbitrary browser-supplied identity header.

If identity integration is not ready initially, use a server-side configured reviewer identity temporarily.

---

# 32. Activity Page

Route:

```text
/activity
```

Potential events:

```text
lead_discovered
research_started
research_completed
lead_scored
product_matched
marketing_action_created
approval_requested
approval_approved
approval_rejected
approval_changes_requested
```

If a dedicated Events API does not exist yet, defer this page.

Never query PostgreSQL directly from the dashboard.

---

# 33. System Page

Route:

```text
/system
```

Show only safe status:

```text
Marketing API      Online / Offline
Database           Reachable / Error
n8n                Later
```

Do not expose:

```text
database password
database hostname
service tokens
internal stack traces
```

---

# 34. Dashboard Security

Required:

```text
Cloudflare Access for human access
Dashboard backend/BFF
server-side dashboard service token
HTTPS
strict CORS / trusted hosts
no service token in browser code
```

Never place the Marketing API credential in:

```text
frontend JavaScript
localStorage
sessionStorage
browser-readable cookies
frontend bundle
```

---

# 35. Dashboard Service Identity

Use a dedicated dashboard credential:

```text
dashboard-mvp1
```

Separate from:

```text
n8n service token
```

Flow:

```text
Browser
   ↓
Dashboard BFF
   │
   │ dashboard service token
   ▼
Marketing API
```

---

# 36. Docker Networking

Recommended:

```text
dashboard
   │
   └── lorrysystem-api-net
            │
            ▼
       marketing-api
            │
            └── lorrysystem-db-net
                        │
                        ▼
                     postgres
```

Rules:

```text
dashboard       ✕ lorrysystem-db-net
n8n             ✕ lorrysystem-db-net
cloudflared     ✕ lorrysystem-db-net

marketing-api   ✓ lorrysystem-db-net
```

---

# 37. API Mapping

| Dashboard Feature | Existing API |
|---|---|
| List companies | `GET /api/companies` |
| Create company | `POST /api/companies` |
| List contacts | `GET /api/contacts` |
| Create contact | `POST /api/contacts` |
| List leads | `GET /api/leads` |
| Create lead | `POST /api/leads` |
| Lead detail | `GET /api/leads/{lead_id}` |
| Lead research | `GET /api/leads/{lead_id}/research` |
| Current score | `GET /api/leads/{lead_id}/scores/current` |
| Score history | `GET /api/leads/{lead_id}/scores` |
| Product matches | `GET /api/leads/{lead_id}/product-matches` |
| Lead actions | `GET /api/leads/{lead_id}/actions` |
| Action detail | `GET /api/actions/{action_id}` |
| Approval list | `GET /api/approvals` |
| Approval detail | `GET /api/approvals/{approval_id}` |
| Approval history | `GET /api/actions/{action_id}/approvals` |
| Approve | `PATCH /api/approvals/{approval_id}/approve` |
| Reject | `PATCH /api/approvals/{approval_id}/reject` |
| Request changes | `PATCH /api/approvals/{approval_id}/request-changes` |

Before coding, confirm exact request/response schemas in current source/OpenAPI.

---

# 38. Error Handling

Translate API responses into user-friendly messages.

Examples:

```text
404
→ Record not found.

409 duplicate company
→ This company already exists.

409 duplicate lead
→ An active lead already exists for this company and ICP.

409 invalid state
→ This action is no longer available in its current status.

422
→ Please check the highlighted fields.

500
→ Something went wrong. Please try again.
```

Technical details belong in server logs.

---

# 39. Loading / Empty States

Every page should support:

```text
loading
empty
error
```

Examples:

```text
No leads yet.
Add your first lead.

No approvals waiting.
You're all caught up.

No Product Matches available yet.
```

---

# 40. Confirmation Dialogs

Require confirmation for:

```text
Reject
Request Changes
Cancel draft action if later exposed
```

---

# 41. MVP1 User Permissions

For MVP1, Parimala may:

```text
view dashboard
view leads
manually create leads
view research
view scores
view product matches
view marketing actions
approve
reject
request changes
```

Do not build full RBAC in MVP1.

---

# 42. No New Database Access

The dashboard must not introduce:

```text
SQLAlchemy DB connection
psycopg DB connection
PostgreSQL credentials
```

The dashboard only uses the Marketing API.

---

# 43. Database Migration Requirement

The dashboard should require:

```text
NO database migration
```

for current MVP1 requirements.

Manual lead entry already uses:

```text
Companies API
Contacts API
Leads API
```

Do not add a separate `manual_lead` table.

---

# 44. n8n Relationship

Dashboard responsibilities:

```text
human input
visibility
human approval
```

n8n responsibilities:

```text
automation
orchestration
```

Target workflow:

```text
Parimala manually adds lead
        ↓
Marketing API
        ↓
Lead = DISCOVERED
        ↓
n8n processes lead
        ↓
Research
        ↓
Scoring
        ↓
Product Matching
        ↓
Marketing Action
        ↓
Approval Queue
        ↓
Parimala reviews
```

Do not duplicate n8n logic in the dashboard.

---

# 45. Manual Lead End-to-End Experience

```text
Parimala logs in
        ↓
Clicks "+ Add Lead"
        ↓
Searches company
        ↓
Selects existing company
        OR
Creates company
        ↓
Selects ICP
        ↓
Adds contact or skips
        ↓
Selects priority
        ↓
Creates lead
        ↓
Lead enters DISCOVERED
        ↓
Dashboard shows lead detail
        ↓
n8n processes lead
        ↓
Dashboard reflects progress
        ↓
Marketing Action reaches approval
        ↓
Parimala approves/rejects/requests changes
```

---

# 46. MVP1 Definition of Done

```text
Cloudflare-protected dashboard accessible          ✓
service credential stays server-side               ✓
dashboard never accesses PostgreSQL directly       ✓

Overview page works                                ✓
Lead list works                                    ✓
basic filters work                                 ✓

Parimala can create/select company                 ✓
Parimala can select ICP                            ✓
Parimala can optionally add contact                ✓
Parimala can select priority                       ✓
Parimala can manually create lead                  ✓
duplicate lead handled cleanly                     ✓

Lead detail works                                  ✓
research visible                                   ✓
current score/history visible                      ✓
Product Matches visible                            ✓
Marketing Actions visible                          ✓

Approval queue works                               ✓
approval snapshot displayed                        ✓
approve works                                      ✓
reject works                                       ✓
request changes works                              ✓

loading states work                                ✓
empty states work                                  ✓
errors are user-friendly                           ✓
laptop UI usable                                   ✓
```

---

# 47. Fastest Build Order

```text
PHASE A — Foundation
1. Create dashboard service
2. Add layout/sidebar
3. Add secure Marketing API client
4. Add Cloudflare Access protection
5. Verify service token stays server-side

PHASE B — Manual Lead Entry
6. Build Leads list
7. Build Add Lead workflow
8. Company search/create
9. ICP selection
10. Optional contact create/select
11. Lead creation
12. Duplicate/error handling
13. Lead detail overview

PHASE C — AI Visibility
14. Research tab
15. Scoring tab
16. Product Matches tab
17. Marketing Actions tab

PHASE D — Human Approval
18. Approval queue
19. Approval detail
20. Approve
21. Reject
22. Request Changes

PHASE E — Polish
23. Overview metrics
24. Empty/loading/error states
25. Activity if Events API exists
26. System status
27. End-to-end validation
```

Highest priority:

```text
Secure Dashboard Shell
        ↓
Lead List
        ↓
Manual Add Lead
        ↓
Lead Details
        ↓
Approval Queue
```

---

# 48. Recommended Page Build Order

```text
1. /leads
2. /leads/new
3. /leads/{lead_id}
4. /approvals
5. /approvals/{approval_id}
6. /dashboard
7. /actions
8. /activity
9. /system
```

Manual lead entry and approval provide the most immediate business value.

---

# 49. Dashboard Validation

Validate:

```text
unauthenticated dashboard blocked
service token never sent to browser
Marketing API failure handled gracefully

company list loads
company creation works
duplicate company handled

contact creation works
duplicate contact handled

lead creation works
lead starts DISCOVERED
ICP required
optional contact works
priority works
duplicate active lead handled

lead detail loads
research renders
score renders
Product Matches render
actions render

pending approvals load
snapshot content correct
approve works
reject requires notes
request changes requires notes
approval state refreshes correctly
```

---

# 50. MVP2 Dashboard Expansion

MVP2 may add:

```text
named users
roles
advanced analytics
campaign/execution monitoring
advanced filtering
bulk operations
reporting
provider execution status
notifications
saved views
```

---

# 51. MVP3 Dashboard Expansion

MVP3 may add:

```text
multiple product workspaces
workspace switcher
fine-grained permissions
enterprise SSO
advanced analytics
cross-workspace reports
administrative controls
audit/security views
```

---

# 52. Immediate Instruction

The dashboard is an MVP1 deliverable.

Current implementation priority:

```text
MVP1 Security Choke Point
        ↓
Dashboard Secure Shell
        ↓
Manual Lead Entry
        ↓
n8n Integration
        ↓
Lead Processing Visibility
        ↓
Approval Queue
        ↓
MVP1 End-to-End Demo
```

Frontend/dashboard work may begin immediately using mock responses while the final MVP1 security gate is being completed.

Do not expose the Marketing API service credential to the browser.

Do not give the dashboard direct PostgreSQL access.

Do not rebuild completed business APIs.
