> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

# LorrySystem MVP1 — GUI Cleanup Progress Tracker

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**Scope:** Lead Management / Dashboard GUI Cleanup  
**Date:** 27 September 2026  
**Current Alembic Head:** `008`  
**Migration 009:** Not required  
**Current Status:** Functional Lead Closure Regression PASSED  
**Next Step:** Dashboard grouping + broader regression  
**Next Major Stage:** Level 2 ZenRows Scraper Fallback

---

## 1. Current Overall Status

```text
Level 1 Web Discovery          ✅ FROZEN
Level 1.1 Discovery Memory     ✅ FROZEN

Lead Closure Backend           ✅ IMPLEMENTED
Sidebar Cleanup                ✅ COMPLETE
Add Lead Intake Hub            ✅ COMPLETE
Lead Group Filters             ✅ COMPLETE
Close Lead GUI                 ✅ COMPLETE
GUI Visual Consistency         ✅ COMPLETE

Functional Closure Regression  ✅ PASSED
Dashboard Grouping Regression  ⏳ NEXT
Import Regression              ⏳ NEXT
Broader GUI/API Regression     ⏳ AFTER THAT
GUI Cleanup Freeze             ⏳ AFTER REGRESSION
Level 2 ZenRows                ⏸ WAITING
```

---

## 2. Locked Architecture Decisions

These decisions are now fixed for MVP1:

```text
Migration 009                  ❌ NOT NEEDED
Lead closure                   → existing status endpoint
Closure metadata               → existing events.metadata JSONB
Hard delete                    ❌ NOT USED
LOST / DISQUALIFIED history    ✅ preserved
Discovery registry             ✅ preserved
Candidate rejection            ≠ Lead closure
```

Existing architecture remains:

```text
Browser
  ↓
Dashboard / BFF
  ↓ server-side X-API-Key
Marketing API
  ↓
PostgreSQL
```

No direct Dashboard → PostgreSQL access.

---

## 3. Lead Closure Backend

Existing endpoint reused:

```text
PATCH /api/leads/{lead_id}/status
```

`LeadStatusUpdate` now supports:

```text
status
reason
note
closed_by
```

Closure reasons:

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

Terminal statuses remain:

```text
CONVERTED
DISQUALIFIED
LOST
```

---

## 4. Closure Audit Behaviour

Closing a Lead creates:

```text
event_type = lead_closed
```

with metadata:

```json
{
  "previous_status": "...",
  "new_status": "LOST or DISQUALIFIED",
  "reason": "...",
  "note": "...",
  "closed_by": "parimala"
}
```

The existing Event timestamp is used as closure time:

```text
events.created_at
```

No new Lead closure columns were added.

---

## 5. Functional Closure Regression — PASSED

Validator result:

```text
PASS: 62
FAIL: 0
RESULT: PASSED
```

Validated successfully:

```text
CONTACTED → LOST / NO_RESPONSE                 ✅
READY_FOR_OUTREACH → LOST                      ✅
REPLIED → LOST / NOT_INTERESTED               ✅
QUALIFIED → DISQUALIFIED / WRONG_FIT          ✅
already LOST → duplicate close rejected       ✅
already DISQUALIFIED → duplicate close reject ✅
CONVERTED → LOST rejected                     ✅
LOST without reason rejected                  ✅
reason/status mismatch rejected               ✅
lead_closed event created                     ✅
event new_status persisted                    ✅
reason persisted                              ✅
note persisted                                ✅
closed_by persisted                           ✅
actor_type / actor_id persisted               ✅
closure timestamp persisted                   ✅
```

No active disposable regression Leads were intentionally left behind.

---

## 6. Disposable Regression Leads Created

```text
CONTACTED_NO_RESPONSE
→ LOST

READY_FOR_OUTREACH_LOST
→ LOST

REPLIED_NOT_INTERESTED
→ LOST

QUALIFIED_WRONG_FIT
→ DISQUALIFIED

CONVERTED_TERMINAL
→ CONVERTED

INVALID_CLOSURE
→ LOST
```

These records are safe regression fixtures and may remain as historical test data unless cleanup is later required.

---

## 7. Sidebar Cleanup — COMPLETE

Old duplicated navigation:

```text
+ Add Lead
Import Leads
```

Updated top-level navigation:

```text
Overview
Leads
+ Add Lead
Discovered Leads
Marketing Actions
Approvals
System
```

`Import Leads` was removed from the sidebar.

`Discovered Leads` remains separate.

---

## 8. Add Lead Intake Hub — COMPLETE

Route:

```text
/leads/new
```

now presents:

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

Existing working Business Card and CSV logic was reused.

---

## 9. Lead Group Filters — IMPLEMENTED

Lead list groups:

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

---

## 10. Close Lead GUI — COMPLETE

Non-terminal Lead Detail pages expose:

```text
[ Close Lead ]
```

Modal options:

```text
No response
Not interested
Wrong fit
Duplicate
Other
```

Optional note is supported.

Terminal Leads do not show the Close Lead action:

```text
CONVERTED
DISQUALIFIED
LOST
```

---

## 11. GUI Visual Consistency — COMPLETE

Fixed visual issues:

```text
Lead Detail 5-card metric wrapping
Add Lead uneven 2 + 1 layout
Unequal intake card sizes
Excess whitespace
Misaligned closure radio buttons
Weak destructive visual styling
```

Current visual status:

```text
Lead Detail layout      ✅
Add Lead intake hub     ✅
Equal card sizing       ✅
Button alignment        ✅
Spacing                 ✅
Close Lead modal        ✅
Radio alignment         ✅
Red danger styling      ✅
Responsive layout       ✅
```

User confirmed the GUI now looks good.

---

## 12. Compile / Build Validation

Marketing API:

```text
python3 -m compileall -q api/app
RESULT: 0
```

Dashboard:

```text
python3 -m compileall -q app
RESULT: 0
```

OpenAPI confirmed:

```text
LeadStatusUpdate
├── status
├── reason
├── note
└── closed_by
```

Dashboard container rebuilt successfully after the GUI changes.

---

## 13. Next Regression — Dashboard Grouping

Using the generated regression records:

### Active

Open:

```text
/leads?view=active
```

Search:

```text
MVP1 Closure Regression
```

Expected:

```text
0 results
```

### Closed

Open:

```text
/leads?view=closed
```

Expected five regression Leads:

```text
CONTACTED_NO_RESPONSE        LOST
READY_FOR_OUTREACH_LOST      LOST
REPLIED_NOT_INTERESTED       LOST
QUALIFIED_WRONG_FIT          DISQUALIFIED
INVALID_CLOSURE              LOST
```

### Converted

Open:

```text
/leads?view=converted
```

Expected:

```text
CONVERTED_TERMINAL
status = CONVERTED
```

When these pass:

```text
Dashboard Grouping Regression ✅
```

---

## 14. Import Regression — PENDING

Existing Dashboard import validator:

```text
scripts/validate_lead_imports.py
```

Previous known result:

```text
PASS: 18
FAIL: 0
RESULT: PASSED
```

Must rerun after GUI cleanup to reconfirm:

```text
import page loads
CSV template downloads
Business Card validation
Business Card review
CSV preview
CSV commit
blank priority → MEDIUM
duplicate handling
error-row export
imported Lead starts DISCOVERED
optional Contact name path
```

---

## 15. Broader Regression — PENDING

Before GUI cleanup freeze, reconfirm:

```text
Candidate Accept
Accepted Candidate → Lead
Discovered Leads list/detail
Manual Add Lead
Business Card import
CSV import
Lead list
Lead detail
Approvals
Marketing Actions
Candidate API
Full backend regression
```

Expected known historical baselines:

```text
Candidate API backend validator
PASS: 102
FAIL: 0
SKIP: 0

Discovered Leads dashboard regression
PASS: 54
FAIL: 0
SKIP: 0

Full backend regression
PASS: 94
FAIL: 0
SKIP: 5
```

Any new failure must be investigated before freeze.

---

## 16. GUI Cleanup Freeze Criteria

The GUI cleanup can be frozen when all of these are true:

```text
[x] Lead Closure backend implemented
[x] Lead Closure functional regression passed
[x] Closure audit metadata verified
[x] Duplicate-close protection verified
[x] Terminal CONVERTED protection verified
[x] Sidebar cleanup complete
[x] Add Lead hub complete
[x] Active / Converted / Closed / All implemented
[x] Visual consistency approved

[ ] Dashboard grouping verified
[ ] Import regression passes
[ ] Candidate / Discovered Leads regression passes
[ ] Broader backend regression passes
[ ] No regression in Approvals
[ ] No regression in Marketing Actions
```

After all remaining checks pass:

```text
GUI Cleanup
→ ✅ FROZEN
```

---

## 17. Important Rules Going Forward

Do NOT:

```text
hard-delete Leads
clear lead_discovery_registry when Lead closes
make LOST Leads automatically rediscoverable
modify frozen Level 1
modify frozen Level 1.1
create migration 009 without a new real requirement
rebuild Business Card or CSV flows unnecessarily
```

Lead closure remains:

```text
Lead
→ LOST / DISQUALIFIED
→ history preserved
→ Event audit preserved
→ discovery memory preserved
```

---

## 18. Immediate Next Task

Run:

```text
1. Dashboard grouping verification
2. Import regression
3. Candidate / Discovered Leads regression
4. Full backend regression
5. Approvals / Marketing Actions regression
```

If all pass:

```text
Functional Closure Regression  ✅ COMPLETE
Full GUI Regression            ✅ COMPLETE
GUI Cleanup                    ✅ FROZEN
Level 2 ZenRows                ▶ NEXT
```

---

## 19. Current MVP1 Status

```text
Backend Foundation             ✅ COMPLETE
Candidate API                  ✅ COMPLETE
Discovered Leads UI            ✅ COMPLETE
Level 1 Web Discovery          ✅ FROZEN
Level 1.1 Discovery Memory     ✅ FROZEN

Lead Closure Backend           ✅ COMPLETE
Lead Closure Regression        ✅ PASSED (62/0)
Sidebar Cleanup                ✅ COMPLETE
Add Lead Intake Hub            ✅ COMPLETE
Lead Group Filters             ✅ COMPLETE
Close Lead GUI                 ✅ COMPLETE
GUI Visual Consistency         ✅ COMPLETE

Dashboard Grouping Regression  ⏳ NEXT
Import Regression              ⏳ PENDING
Broader Regression             ⏳ PENDING
GUI Cleanup Freeze             ⏳ AFTER REGRESSION

Level 2 ZenRows                ⏸ WAITING
```
