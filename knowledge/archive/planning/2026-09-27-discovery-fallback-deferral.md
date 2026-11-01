> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

# LorrySystem MVP1 — Deferred Level 2 & Level 3 Reminder

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1 — Lead Discovery  
**Status:** ON HOLD  
**Created:** 27 September 2026  

---

## Why This Is On Hold

Level 2 and Level 3 Lead Discovery are intentionally paused while the remaining MVP1 GUI / lead-management work and other higher-priority items are completed.

Do **not** restart Level 2 or Level 3 until the current GUI cleanup and broader regression work are finished and frozen.

---

# Current Lead Discovery Status

```text
Level 1 Web Discovery          ✅ FROZEN
Level 1.1 Discovery Memory     ✅ FROZEN

Lead Closure Backend           ✅ COMPLETE
Lead Closure Regression        ✅ PASSED
Sidebar Cleanup                ✅ COMPLETE
Add Lead Intake Hub            ✅ COMPLETE
Lead Group Filters             ✅ COMPLETE
Close Lead GUI                 ✅ COMPLETE
GUI Visual Consistency         ✅ COMPLETE

Dashboard Grouping Regression  ⏳ PENDING
Import Regression              ⏳ PENDING
Broader Regression             ⏳ PENDING
GUI Cleanup Freeze             ⏳ PENDING

Level 2 ZenRows                ⏸ ON HOLD
Level 3 Social Discovery       ⏸ ON HOLD
```

---

# Resume Condition

Return to Level 2 / Level 3 only after:

```text
[ ] Dashboard grouping regression passes
[ ] Import regression passes
[ ] Candidate / Discovered Leads regression passes
[ ] Full backend regression passes
[ ] Approvals regression passes
[ ] Marketing Actions regression passes
[ ] GUI Cleanup is marked FROZEN
[ ] Other priority MVP1 work is complete
```

---

# Level 2 — ZenRows Scraper Fallback

## Objective

Level 2 exists only for public webpages that Level 1 cannot fetch successfully.

Input source:

```text
n8n Data Table:
lead_discovery_registry
```

Filter:

```text
status = LEVEL2_REQUIRED
```

## Planned Provider

```text
ZenRows
```

Use ZenRows as the primary MVP1 fallback provider.

Do not redesign Level 1.

Level 2 is only an alternate retrieval method.

## Intended Flow

```text
lead_discovery_registry
        ↓
status = LEVEL2_REQUIRED
        ↓
ZenRows
        ↓
Rendered HTML
        ↓
Existing HTML → Clean Text
        ↓
Existing Cheap Relevance Gate
        ↓
Existing OpenAI Extraction + ICP
        ↓
Existing Candidate API
        ↓
Update Discovery Registry
```

## Level 2 Rules

```text
✓ Process only LEVEL2_REQUIRED
✓ Keep Level 1 / Level 1.1 frozen
✓ Reuse existing Clean Text pipeline
✓ Reuse existing relevance gate
✓ Reuse existing OpenAI Extraction + ICP
✓ Reuse existing Candidate API
✓ Reuse existing deduplication
✓ Reuse existing source traceability
✓ Reuse human review
✓ Track ZenRows provider usage
✓ Track fallback attempts
✓ Track success / failure
✓ Track credits / cost
✓ Respect retry windows
✓ Respect 429 / Retry-After
✓ Avoid aggressive retry on 403

✕ Do not bypass login
✕ Do not bypass CAPTCHA
✕ Do not access private pages
✕ Do not create a separate Candidate pipeline
✕ Do not connect n8n directly to PostgreSQL
```

## Planned Level 2 Registry Fields

Add to the n8n Data Table when Level 2 work resumes:

```text
level2_attempted_at
level2_provider
level2_result
level2_credits_used
level2_retry_after
```

Recommended provider value:

```text
ZENROWS
```

## Suggested ZenRows Strategy

Start cheap and escalate only when needed:

```text
Level 1 Failed
      ↓
ZenRows Attempt 1
JS rendering
      ↓
Success?
 ├── YES → Existing downstream pipeline
 └── NO
      ↓
ZenRows Attempt 2
JS rendering + stronger proxy option
      ↓
Success?
 ├── YES → Existing downstream pipeline
 └── NO  → mark fallback failure / retry later
```

Do not send normal successful Level 1 URLs through ZenRows.

## Level 2 Validation

When resumed, validate:

```text
[ ] LEVEL2_REQUIRED row selected
[ ] ZenRows request succeeds
[ ] Rendered HTML returned
[ ] Clean Text works
[ ] Relevance Gate works
[ ] AI Extraction + ICP works
[ ] Candidate API works
[ ] Candidate dedup still works
[ ] Source traceability preserved
[ ] Registry updates correctly
[ ] Provider recorded
[ ] Credits/cost recorded
[ ] Failure path works
[ ] Retry path works
[ ] CAPTCHA/login/private content stops safely
```

---

# Level 3 — Controlled Social Discovery

## Start Condition

Do not begin Level 3 until:

```text
Level 2 is implemented
Level 2 is validated
Level 2 is stable
```

## Objective

Use controlled public / permitted social sources to discover or enrich companies.

Potential signals:

```text
fleet expansion
driver hiring
new depots
new branches
vehicle purchases
new contracts
digitisation activity
safety activity
fleet-related business growth
```

## Preferred Source Order

```text
1. Official social APIs
2. Approved third-party providers
3. Public / search-indexed company pages
```

## Level 3 Rules

```text
✓ Reuse Lead Candidate system
✓ Reuse Candidate Sources
✓ Reuse deduplication
✓ Reuse human review
✓ Preserve source traceability
✓ Enrich existing Candidates when possible

✕ No private profile scraping
✕ No login bypass
✕ No CAPTCHA bypass
✕ No mass LinkedIn member scraping
✕ No unrestricted social harvesting
✕ No automatic outreach
```

## Intended Level 3 Flow

```text
Official API / Provider / Public Indexed Social Page
        ↓
n8n
        ↓
Normalize Social Data
        ↓
AI Signal Extraction
        ↓
Company Resolution
        ↓
ICP Evaluation
        ↓
Deduplication
        ↓
Existing Candidate?
   ┌──────────┴──────────┐
  YES                    NO
   │                      │
Enrich Candidate      Create Candidate
   │                      │
   └──────────┬───────────┘
              ↓
         Human Review
```

## Level 3 Validation

When resumed:

```text
[ ] Approved social source selected
[ ] Provider/API credentials stored securely
[ ] Public/permitted data retrieved
[ ] Company resolution works
[ ] Buying signals extracted
[ ] ICP evaluation works
[ ] Duplicate social sources prevented
[ ] Existing Candidates can be enriched
[ ] New Candidates can be created
[ ] Dashboard shows social evidence
[ ] Human review remains mandatory
[ ] No private/restricted scraping used
[ ] Cost remains within MVP1 budget
```

---

# Important Frozen Components

Do not modify unless a real regression or new requirement appears:

```text
Level 1 Web Discovery
Level 1.1 Discovery Memory Gate
Brave Search logic
URL normalization
Discovery Registry
Directory / aggregator protection
HTML → Clean Text
Cheap Relevance Gate
OpenAI Extraction + ICP
Candidate Eligibility
Candidate Payload
Candidate API
Candidate source traceability
Discovered Leads flow
```

---

# Important Operational Rule

```text
DO NOT CLEAR:
lead_discovery_registry
```

It is now operational memory and is also the future input queue for Level 2.

---

# When Returning to This File

Resume in this exact order:

```text
1. Confirm GUI cleanup is frozen
2. Inspect lead_discovery_registry
3. Count LEVEL2_REQUIRED rows
4. Create ZenRows credential in n8n
5. Add Level 2 registry fields if needed
6. Build provider-neutral Level 2 fallback section
7. Connect ZenRows
8. Route only LEVEL2_REQUIRED rows
9. Rejoin existing frozen downstream pipeline
10. Validate Level 2
11. Freeze Level 2
12. Design Level 3 provider/source strategy
13. Implement controlled social discovery
14. Validate Level 3
15. Run final Lead Discovery regression
```

---

# Final Reminder

```text
Level 2 = difficult PUBLIC webpage retrieval fallback
Level 3 = controlled social discovery / enrichment
```

Do not rebuild the existing discovery architecture.

Both stages must plug into the already-working Candidate / ICP / deduplication / human-review pipeline.
