---
title: LorrySystem MVP1 — Lead Management GUI Cleanup Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
date: 2026-09-27
status: ready-to-build
scope: Dashboard / Lead Management Cleanup
current_alembic_head: "008"
next_migration_id_if_needed: "009"
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.


# LorrySystem MVP1 — Lead Management GUI Cleanup Handoff

## 1. Purpose

This update should be completed **before Level 2 ZenRows integration**.

Two GUI / lead-management inconsistencies need to be fixed:

```text
1. Accepted Leads need a clean way to be closed when there is no response.
2. Sidebar navigation is cluttered because Add Lead and Import Lead are separate.
```

The goal is to make the operator workflow cleaner without changing the frozen Level 1 / Level 1.1 discovery pipeline.

---

# 2. Current Behaviour

Current discovery flow:

```text
Discovered Lead Candidate
        ↓
Human Accept
        ↓
Company / Contact / Lead created or reused
        ↓
Lead enters normal Lead pipeline
```

The current Lead lifecycle already includes terminal outcomes such as:

```text
CONVERTED
DISQUALIFIED
LOST
```

Problem:

```text
Lead is accepted
    ↓
Lead is contacted
    ↓
Other party never responds
    ↓
Lead remains visible in active working list
```

We need a mechanism to close that Lead without deleting its history.

---

# 3. Important Design Rule

Do NOT hard-delete a Lead simply because there was no response.

Correct behaviour:

```text
No response
    ↓
Close Lead
    ↓
status = LOST
    ↓
reason = NO_RESPONSE
    ↓
Lead disappears from Active Leads
    ↓
History remains available
```

This preserves:

```text
company history
contact history
research
scores
product matches
marketing actions
approval history
events
discovery memory
```

---

# 4. Candidate Rejection vs Lead Closure

These are separate concepts.

```text
Candidate rejection
= company was not accepted as an official Lead

Lead closure
= company became a Lead but the sales/outreach attempt is finished
```

Therefore:

```text
Candidate
→ Reject

Lead
→ Close / Lost / Disqualified
```

Do not reuse Candidate rejection for active Leads.

---

# 5. Lead Lifecycle

Keep the existing Lead lifecycle.

Conceptually:

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
    ├── REPLIED
    │      ↓
    │   CONVERTED
    │
    └── No response / no opportunity
           ↓
          LOST
```

Other terminal path:

```text
Lead determined unsuitable
    ↓
DISQUALIFIED
```

---

# 6. New GUI Action — Close Lead

Add a Lead-level action:

```text
[ Close Lead ]
```

Recommended placement:

```text
Lead Detail Page
```

Do not place destructive/terminal actions as the primary button.

Example:

```text
Lead: ABC Logistics Sdn Bhd

Status: CONTACTED
Last Activity: 12 days ago

[ Edit ]
[ View Actions ]
[ Close Lead ]
```

---

# 7. Close Lead Modal

When the operator clicks:

```text
Close Lead
```

show:

```text
Close Lead

Reason:

○ No response
○ Not interested
○ Wrong fit
○ Duplicate
○ Other

Optional note:
[________________________]

[Cancel] [Close Lead]
```

---

# 8. Closure Reasons

Recommended internal values:

```text
NO_RESPONSE
NOT_INTERESTED
WRONG_FIT
DUPLICATE
OTHER
```

Display labels can be:

```text
No response
Not interested
Wrong fit
Duplicate
Other
```

---

# 9. Status Mapping

Default mapping:

```text
NO_RESPONSE
→ LOST

NOT_INTERESTED
→ LOST

OTHER
→ LOST
```

Possible mapping:

```text
WRONG_FIT
→ DISQUALIFIED

DUPLICATE
→ DISQUALIFIED
```

Do not change lifecycle rules blindly.

First inspect the existing Lead status-transition service and allowed transitions.

---

# 10. Database Decision

Current migration head:

```text
008
```

Before changing the database, inspect whether the existing Lead/Event model can already record a closure reason.

Check for existing fields such as:

```text
reason
notes
status_reason
closed_reason
disqualification_reason
metadata
event payload
```

If the existing schema can preserve the reason safely:

```text
NO NEW MIGRATION
```

If a new persistent field is required, use the next real migration:

```text
009
```

Possible fields:

```text
closed_reason
closed_note
closed_at
```

Do NOT create migration 009 unless necessary.

---

# 11. Preferred Event / Audit Behaviour

Closing a Lead should create an event.

Example:

```text
event_type:
lead_closed

payload:
{
  "previous_status": "CONTACTED",
  "new_status": "LOST",
  "reason": "NO_RESPONSE",
  "note": "...",
  "closed_by": "parimala"
}
```

If the existing event system already supports Lead status changes, reuse it.

Do not build a second audit system.

---

# 12. Backend API

Inspect the existing Lead status endpoint first.

If the existing endpoint supports:

```text
PATCH /api/leads/{lead_id}/status
```

and can safely carry reason/note metadata, extend or reuse it.

Preferred request shape:

```json
{
  "status": "LOST",
  "reason": "NO_RESPONSE",
  "note": "No reply after follow-up."
}
```

If that endpoint cannot support closure metadata cleanly, consider:

```text
POST /api/leads/{lead_id}/close
```

Example:

```json
{
  "reason": "NO_RESPONSE",
  "note": "No reply after follow-up."
}
```

Prefer reusing existing API conventions over adding unnecessary routes.

---

# 13. Closure Validation Rules

The backend must validate:

```text
Lead exists
Lead is not already terminal
Reason is valid
Status transition is allowed
closed_by is known if required
```

Reject:

```text
closing CONVERTED lead accidentally
closing already LOST lead again
invalid reason
blank required note for OTHER if policy requires it
```

---

# 14. Active vs Closed Leads

The Leads page should separate working Leads from completed/closed Leads.

Recommended UI:

```text
Leads

[ Active ] [ Converted ] [ Closed ] [ All ]
```

For MVP1, this is sufficient.

---

# 15. Active Lead Definition

Recommended Active filter:

```text
DISCOVERED
RESEARCHING
QUALIFIED
READY_FOR_OUTREACH
CONTACTED
REPLIED
```

---

# 16. Closed Lead Definition

Closed should include:

```text
LOST
DISQUALIFIED
```

Converted remains separate:

```text
CONVERTED
```

Default Leads view:

```text
Active
```

---

# 17. Lead Detail — Activity Age

Add useful operator context where practical:

```text
Created:
<date>

Last Updated:
<date>

Last Activity:
<date or derived value>
```

Possible display:

```text
Last activity: 12 days ago
```

Use existing timestamps/events where possible. Do not invent a second activity system.

---

# 18. Stale Lead Indicator

Optional MVP1 GUI improvement:

```text
⚠ No activity for 14 days
```

Do NOT automatically close stale Leads in this update.

For now:

```text
system may highlight
human decides
```

Automatic stale-lead handling can be added later through n8n if required.

---

# 19. Sidebar Cleanup

Current problem:

```text
Add Lead
Import Lead
```

are both top-level navigation items.

Remove:

```text
Import Lead
```

from the sidebar.

---

# 20. Recommended Sidebar

Preferred:

```text
Dashboard

Leads
├── All Leads
├── Add Lead
└── Discovered Leads

Approvals
Actions
System
```

If nested navigation is not supported cleanly:

```text
Dashboard
Leads
Add Lead
Discovered Leads
Approvals
Actions
System
```

Still remove the standalone Import Lead entry.

---

# 21. Add Lead Page

The Add Lead page becomes the single entry point for operator-supplied Leads.

Recommended layout:

```text
                    Add Lead

How would you like to add leads?

┌─────────────────────────┐
│ Manual Entry            │
│ Add a single lead       │
└─────────────────────────┘

┌─────────────────────────┐
│ Business Card           │
│ Upload and review card  │
└─────────────────────────┘

┌─────────────────────────┐
│ CSV Import              │
│ Import multiple leads   │
└─────────────────────────┘
```

Buttons:

```text
[ Add Manually ]
[ Upload Business Card ]
[ Import CSV ]
```

---

# 22. Existing Functionality Must Be Reused

Do NOT rebuild:

```text
Manual Lead form
Business Card import
CSV preview
CSV validation
CSV commit
duplicate handling
error-row export
```

The new Add Lead page should route to or embed the existing working flows.

---

# 23. Routes

Keep existing routes where possible.

Example:

```text
/leads/new
```

can become the Add Lead landing page.

Existing import routes can remain behind buttons.

Possible future paths:

```text
/leads/new/manual
/leads/new/business-card
/leads/new/csv
```

Do not rename working routes unless necessary.

---

# 24. Breadcrumbs

Recommended:

```text
Leads > Add Lead > CSV Import
```

and:

```text
Leads > Lead Detail
```

---

# 25. Discovered Leads Remains Separate

Do NOT merge:

```text
Discovered Leads
```

into Add Lead.

Reason:

```text
Add Lead
= operator-supplied Leads

Discovered Leads
= AI-discovered Candidates awaiting review
```

Keep Discovered Leads as a separate Lead-related navigation item.

---

# 26. Interaction With Discovery Memory

When a Candidate is accepted and becomes a Lead:

```text
lead_discovery_registry
```

already remembers the company.

If that Lead is later closed as:

```text
LOST
```

do NOT clear or delete its Discovery Registry record.

The discovery system should continue remembering that this company has already been processed.

---

# 27. Re-Discovery Policy

For this GUI update:

```text
do NOT automatically make LOST Leads discoverable again
```

Future policy can decide whether a LOST company may be retried after:

```text
90 days
180 days
1 year
manual reset
```

That is outside this cleanup.

---

# 28. No Hard Delete

Do not add normal operator Lead deletion.

The operator should use:

```text
Close Lead
```

instead.

---

# 29. Backend Work Summary

Inspect first, then implement only what is needed.

Potential work:

```text
Lead close/status API
closure reason persistence
closure note persistence
closed_at timestamp
event logging
status-transition validation
Lead list filtering
```

---

# 30. GUI Work Summary

Implement:

```text
1. Remove standalone Import Lead sidebar item
2. Make Add Lead the intake hub
3. Add Manual / Business Card / CSV choices
4. Add Active / Converted / Closed / All filters
5. Default Leads page to Active
6. Add Close Lead button
7. Add closure-reason modal
8. Map No Response → LOST
9. Preserve Lead history
10. Show last activity / age where practical
```

---

# 31. API Filtering

If the Lead API already supports status filtering, reuse it.

If it only supports one status at a time, the Dashboard/BFF can group/filter server-side for MVP1.

Avoid unnecessary API redesign.

---

# 32. Regression Requirements

After implementation verify:

```text
Candidate Accept still works
Accepted Candidate becomes Lead
Manual Add Lead still works
Business Card intake still works
CSV import still works
Lead list still loads
Lead detail still loads
Lead close works
LOST Lead disappears from Active
LOST Lead appears in Closed
Converted remains separate
Discovered Leads remains unchanged
Approvals remain unchanged
Actions remain unchanged
```

---

# 33. Closure Tests

Test:

```text
1. CONTACTED → LOST / NO_RESPONSE
2. READY_FOR_OUTREACH → LOST
3. REPLIED → LOST / NOT_INTERESTED
4. QUALIFIED → DISQUALIFIED / WRONG_FIT
5. already LOST → reject duplicate close
6. already DISQUALIFIED → reject duplicate close
7. CONVERTED → prevent accidental close unless explicitly supported
8. closure reason persists
9. closure note persists if implemented
10. event/audit record exists
```

---

# 34. Sidebar Tests

Verify:

```text
Import Lead removed from sidebar
Add Lead visible
Discovered Leads visible
Manual entry accessible
Business Card accessible
CSV Import accessible
back navigation works
breadcrumbs work
```

---

# 35. Migration Decision Checklist

Before creating migration 009:

```text
[ ] inspect Lead model
[ ] inspect Lead schemas
[ ] inspect Lead service
[ ] inspect Events model
[ ] inspect existing status-change endpoint
[ ] determine whether closure reason can already be stored
```

If existing structures are sufficient:

```text
NO MIGRATION
```

If persistent closure fields are needed:

```text
Migration 009
```

Do not modify applied migrations.

---

# 36. Frozen Components

Do NOT change:

```text
Level 1 Web Discovery
Level 1.1 Discovery Memory Gate
Brave Search logic
URL normalization
Relevance Gate
OpenAI Extraction + ICP
Candidate API
Candidate source traceability
Discovered Leads Candidate flow
```

This task is limited to:

```text
Lead management
Dashboard navigation
Lead closure UX
```

---

# 37. Recommended Build Order

```text
1. Inspect current Lead model/schema/status service
2. Inspect current Lead dashboard routes/templates
3. Inspect sidebar template
4. Decide closure-reason persistence method
5. Add/extend Lead close API
6. Add Lead close validation
7. Add event/audit record
8. Add Active / Converted / Closed / All filters
9. Add Close Lead button/modal
10. Remove Import Lead sidebar item
11. Convert Add Lead page into intake landing page
12. Link Manual / Business Card / CSV flows
13. Add breadcrumbs if appropriate
14. Run dashboard regression
15. Run Lead lifecycle regression
16. Verify Candidate → Lead flow still works
17. Freeze GUI cleanup
18. Return to Level 2 ZenRows
```

---

# 38. Definition of Done

```text
Standalone Import Lead sidebar item removed          ✓
Add Lead becomes intake hub                          ✓
Manual Entry accessible                              ✓
Business Card accessible                             ✓
CSV Import accessible                                ✓
Discovered Leads remains separate                    ✓

Lead can be closed without deletion                  ✓
No Response maps to LOST                             ✓
Closure reason preserved                             ✓
History preserved                                    ✓
Terminal Lead hidden from Active                     ✓
Terminal Lead visible under Closed                   ✓
Converted Lead handled separately                    ✓
Existing Lead lifecycle remains valid                ✓

Candidate → Lead acceptance still works              ✓
Business Card intake regression passes               ✓
CSV intake regression passes                         ✓
Lead page regression passes                          ✓
Dashboard regression passes                          ✓
```

---

# 39. Immediate Next Task

Start with inspection, not coding.

Inspect:

```text
Lead SQLAlchemy model
Lead Pydantic schemas
Lead router
Lead service/status transition logic
Events model/service
Dashboard Lead routes
Dashboard sidebar template
Add Lead template
CSV Import template/routes
Business Card template/routes
```

Then answer:

```text
Can closure reason be persisted without migration 009?
```

After that implement:

```text
Close Lead
+
Sidebar / Add Lead cleanup
```

Do not begin Level 2 until this GUI cleanup passes regression.
