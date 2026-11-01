> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

# LorrySystem MVP1 — Lead Management GUI Cleanup Progress

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**Scope:** Lead Management / Dashboard GUI Cleanup  
**Date:** 27 September 2026  
**Current Alembic Head:** `008`  
**Migration 009:** Not required  
**Current Status:** GUI cleanup visually complete; functional closure regression still pending  
**Next Major Stage After Regression:** Level 2 Scraper Fallback

---

## 1. Scope

This update was started before Level 2 ZenRows integration to fix two operational inconsistencies:

```text
1. Accepted Leads needed a clean way to be closed when there is no response.
2. Add Lead and Import Lead were duplicated as separate top-level navigation items.
```

The frozen Level 1 / Level 1.1 discovery pipeline was not changed.

---

## 2. Frozen Discovery Components

```text
Level 1 Web Discovery
Level 1.1 Discovery Memory Gate
Brave Search logic
URL normalization
Website fetch logic
Relevance Gate
OpenAI Extraction + ICP
Candidate API
Candidate source traceability
Discovered Leads Candidate flow
```

Current status:

```text
Level 1       ✅ FROZEN
Level 1.1     ✅ FROZEN
Level 2       ⏳ NEXT AFTER GUI REGRESSION
```

---

## 3. Backend Inspection Result

The existing Lead lifecycle already supports active Leads transitioning to terminal states:

```text
LOST
DISQUALIFIED
```

Existing API route:

```text
PATCH /api/leads/{lead_id}/status
```

The existing `events` table already provides:

```text
event_type
entity_type
entity_id
actor_type
actor_id
metadata JSONB
created_at
```

Decision:

```text
Migration 009 is NOT required.
```

Closure metadata is stored in the existing Event system.

---

## 4. Lead Closure Backend — IMPLEMENTED

`LeadStatusUpdate` now supports:

```text
status
reason
note
closed_by
```

Supported closure reasons:

```text
NO_RESPONSE
NOT_INTERESTED
WRONG_FIT
DUPLICATE
OTHER
```

Status mapping:

```text
NO_RESPONSE      → LOST
NOT_INTERESTED   → LOST
OTHER            → LOST
WRONG_FIT        → DISQUALIFIED
DUPLICATE        → DISQUALIFIED
```

Validation now rejects:

```text
invalid closure reason
reason/status mismatch
closure reason on a non-closure transition
re-closing LOST
re-closing DISQUALIFIED
CONVERTED → LOST
CONVERTED → DISQUALIFIED
```

---

## 5. Closure Audit Behaviour

Closing a Lead creates:

```text
event_type = lead_closed
```

with metadata:

```json
{
  "previous_status": "...",
  "new_status": "LOST or DISQUALIFIED",
  "reason": "NO_RESPONSE / NOT_INTERESTED / WRONG_FIT / DUPLICATE / OTHER",
  "note": "...",
  "closed_by": "parimala"
}
```

The Event `created_at` timestamp is used as the closure timestamp.

No new `closed_at` field was added to `leads`.

---

## 6. Backend Validation

OpenAPI confirmed `LeadStatusUpdate` contains:

```text
status
reason
note
closed_by
```

Compile result:

```text
python3 -m compileall -q api/app
RESULT: 0
```

Backend status:

```text
Schema loaded        ✅
Router updated       ✅
Service updated      ✅
Closure validation   ✅
Event metadata       ✅
Migration required   ❌
```

---

## 7. Dashboard Routes — UPDATED

Current Lead routes include:

```text
GET  /leads
GET  /leads/new
GET  /leads/new/manual
POST /leads/new
GET  /leads/import
POST /leads/{lead_id}/close
GET  /leads/{lead_id}
```

The existing Business Card and CSV routes remain intact and are reused.

---

## 8. Sidebar Cleanup — COMPLETE

The standalone:

```text
Import Leads
```

entry was removed from the sidebar.

Current navigation concept:

```text
Overview
Leads
+ Add Lead
Discovered Leads
Marketing Actions
Approvals
System
```

`Discovered Leads` remains separate because it represents AI-discovered Candidates awaiting human review.

---

## 9. Add Lead Intake Hub — COMPLETE

Route:

```text
/leads/new
```

now acts as the single operator intake hub.

Options:

```text
Manual Entry
Business Card
CSV Import
```

Routes:

```text
Manual Entry
→ /leads/new/manual

Business Card
→ /leads/import#business-card

CSV Import
→ /leads/import#csv-import
```

Existing functionality was preserved:

```text
Manual Lead creation
Business Card upload
Business Card extraction
Business Card review
CSV template
CSV upload
CSV preview
CSV validation
CSV commit
Duplicate handling
Error-row export
```

---

## 10. Leads Page Filtering — IMPLEMENTED

The Leads page now provides:

```text
Active
Converted
Closed
All
```

Default:

```text
Active
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

Converted:

```text
CONVERTED
```

Closed:

```text
LOST
DISQUALIFIED
```

Existing search, status and priority filters remain available.

---

## 11. Close Lead GUI — IMPLEMENTED

Non-terminal Lead Detail pages now show:

```text
[ Close Lead ]
```

The action is hidden for:

```text
CONVERTED
DISQUALIFIED
LOST
```

The modal provides:

```text
No response
Not interested
Wrong fit
Duplicate
Other

Optional note
```

Submission route:

```text
POST /leads/{lead_id}/close
```

The Dashboard maps the selected reason to the correct terminal status and sends it through the Marketing API.

---

## 12. Lead Detail Improvements — COMPLETE

Lead Detail now displays:

```text
Current Score
Status
Priority
Created
Last Updated
```

Breadcrumb:

```text
Leads > Company Name
```

Closure success and error messages are supported.

---

## 13. GUI Visual Consistency Pass — COMPLETE

Issues found after the first GUI implementation:

```text
5th Lead metric card wrapped onto its own row
Add Lead used an uneven 2 + 1 card layout
Add Lead cards had inconsistent visual balance
Excess empty space on the Add Lead page
Close Lead radio buttons were misaligned
Close Lead reason choices did not visually look like terminal actions
```

Fixes applied:

```text
Lead Detail metric cards aligned consistently
Add Lead uses 3 equal-width cards on wide screens
Add Lead cards use equal heights
Action buttons align consistently
Responsive layouts added
Close Lead choices use red-tinted bordered boxes
Radio controls vertically align with reason labels
Selected closure reason gets stronger red highlighting
Close Lead submit button uses destructive red styling
Modal spacing and sizing improved
```

Visual result:

```text
User confirmed: all looks good
```

---

## 14. Dashboard Compile / Build Status

Dashboard compile:

```text
python3 -m compileall -q app
RESULT: 0
```

Dashboard container rebuilt successfully after the GUI changes.

Visual verification:

```text
Lead Detail layout      ✅
Add Lead intake hub     ✅
Card consistency        ✅
Whitespace / spacing    ✅
Close Lead modal style  ✅
Radio alignment         ✅
Danger styling          ✅
```

---

## 15. Definition of Done Progress

### GUI / Navigation

```text
[x] Standalone Import Lead sidebar item removed
[x] Add Lead becomes intake hub
[x] Manual Entry accessible
[x] Business Card accessible
[x] CSV Import accessible
[x] Discovered Leads remains separate
[x] Leads page defaults to Active
[x] Active / Converted / Closed / All views added
[x] Add Lead card sizes consistent
[x] Lead Detail metric layout polished
[x] Close Lead modal visually polished
```

### Backend / Lead Closure

```text
[x] Existing status endpoint reused
[x] Closure reasons added
[x] Reason/status mapping added
[x] Lead closure event added
[x] No hard-delete behaviour
[x] History preservation design retained
[x] Migration 009 avoided
[x] OpenAPI schema verified
[x] Backend compile passed
```

### Pending Functional Regression

```text
[ ] Create controlled test Lead
[ ] CONTACTED → LOST / NO_RESPONSE
[ ] READY_FOR_OUTREACH → LOST
[ ] REPLIED → LOST / NOT_INTERESTED
[ ] QUALIFIED → DISQUALIFIED / WRONG_FIT
[ ] already LOST → duplicate close rejected
[ ] already DISQUALIFIED → duplicate close rejected
[ ] CONVERTED → close rejected
[ ] closure reason persists in Event
[ ] closure note persists in Event
[ ] closed_by persists in Event
[ ] LOST Lead disappears from Active
[ ] LOST Lead appears in Closed
[ ] DISQUALIFIED Lead appears in Closed
[ ] Converted remains separate
[ ] Candidate Accept still works
[ ] Accepted Candidate becomes Lead
[ ] Manual Add Lead still works
[ ] Business Card intake regression passes
[ ] CSV import regression passes
[ ] Lead list still loads
[ ] Lead detail still loads
[ ] Discovered Leads remains unchanged
[ ] Approvals remain unchanged
[ ] Marketing Actions remain unchanged
```

---

## 16. Important Rules Going Forward

Do NOT:

```text
hard-delete Leads
clear lead_discovery_registry when a Lead is closed
automatically make LOST Leads discoverable again
modify Level 1
modify Level 1.1
create migration 009 unless a future requirement truly needs it
rebuild Business Card / CSV functionality
```

Lead closure remains:

```text
Lead
→ LOST / DISQUALIFIED
→ history preserved
→ discovery memory preserved
```

---

## 17. Immediate Next Task

Run the controlled Lead closure regression.

Recommended first test:

```text
Create or use a disposable test Lead
        ↓
Advance it to CONTACTED
        ↓
Close Lead
        ↓
Reason = NO_RESPONSE
        ↓
Expected status = LOST
        ↓
Verify:
  Lead disappears from Active
  Lead appears in Closed
  lead_closed Event exists
  reason = NO_RESPONSE
  note preserved
  closed_by = parimala
```

After the functional regression passes:

```text
GUI Cleanup
→ FREEZE
```

Then continue:

```text
Level 2 ZenRows Scraper Fallback
```

---

## 18. Current MVP1 Status

```text
Backend Foundation             ✅ COMPLETE
Candidate API                  ✅ COMPLETE
Discovered Leads UI            ✅ COMPLETE
Level 1 Web Discovery          ✅ FROZEN
Level 1.1 Discovery Memory     ✅ FROZEN
Lead Closure Backend           ✅ IMPLEMENTED
Sidebar Cleanup                ✅ COMPLETE
Add Lead Intake Hub            ✅ COMPLETE
Lead Group Filters             ✅ COMPLETE
Close Lead GUI                 ✅ COMPLETE
GUI Visual Consistency         ✅ COMPLETE
Functional Closure Regression  ⏳ NEXT
GUI Cleanup Freeze             ⏳ AFTER REGRESSION
Level 2 Scraper Fallback       ⏸ WAITING
```
