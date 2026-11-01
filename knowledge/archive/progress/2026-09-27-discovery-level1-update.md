> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

# LorrySystem MVP1 — Lead Discovery Progress Tracker — Level 1 Complete

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**Scope:** Lead Discovery  
**Last Updated:** 27 September 2026  
**Current Database Migration Head:** `008`

---

## 1. Current Overall Status

### Lead Discovery

- [x] Business Card intake
- [x] CSV intake
- [x] Lead Candidate staging layer
- [x] Candidate Source staging layer
- [x] Candidate API
- [x] Discovered Leads dashboard
- [x] Candidate detail page
- [x] Accept / Edit / Reject workflow
- [x] Level 1 Web Discovery
- [x] Search API integration
- [x] URL filtering
- [x] Normal website fetching
- [x] Fetch classification
- [x] HTML to readable text extraction
- [x] Cheap relevance gate
- [x] OpenAI structured company extraction
- [x] Contact quality protection
- [x] Fleet evidence classification
- [x] ICP evaluation
- [x] Confidence calibration
- [x] Candidate payload construction
- [x] Candidate creation through Marketing API
- [x] Candidate deduplication handling
- [x] Source traceability
- [x] Discovered Leads insertion
- [x] Human review queue
- [x] Level 1 clean-database insertion test
- [x] Existing Candidate deduplication test
- [x] Existing Active Lead short-circuit test
- [x] Final Level 1 E2E validator
- [x] Level 1 freeze readiness confirmed
- [ ] Level 2 scraper fallback
- [ ] Level 2 validation
- [ ] Level 3 controlled social discovery
- [ ] Level 3 validation
- [ ] Final Lead Discovery regression


---

# 2. Core Marketing API Status — COMPLETE

The Lead Discovery pipeline now sits on top of the completed MVP1 Marketing API business layer.

### Completed API Modules

```text
Companies API                 COMPLETE
Contacts API                  COMPLETE
Leads API                     COMPLETE
Research API                  COMPLETE
Scoring API                   COMPLETE
Product Matching API          COMPLETE
Marketing Actions API         COMPLETE
Approval API                  COMPLETE
Candidate API                 COMPLETE
```

### Validated Core Behaviour

```text
Lead duplicate protection
├── API-level company + ICP protection
└── PostgreSQL partial unique protection

Research
├── Historical research runs preserved
├── PENDING / RUNNING / COMPLETED / PARTIAL / FAILED
├── Research sources preserved
└── Research completion does not auto-qualify a Lead

Scoring
├── Historical score rows preserved
├── One current score per Lead
├── leads.current_score synchronized
├── Usable research prerequisite enforced
└── No automatic qualification side effect

Product Matching
├── One mutable match per Lead + Product
├── Repeat matching updates the same row
└── Lead status/current score remain protected

Marketing Actions
├── DRAFT lifecycle
├── Channel/action validation
├── Scored Lead + ProductMatch prerequisites
├── Draft-only editing
├── Cancellation controls
└── Event logging

Approvals
├── Immutable approval snapshot
├── One active PENDING request per action
├── Approve / Reject workflow
├── Action synchronization
└── Event logging
```

### Core API Validation Snapshot

```text
Research API            PASSED
Scoring API             PASSED
Product Matching API    PASSED
Marketing Actions API   PASSED
Approval API            PASSED
```

A later full-stack regression across the downstream Marketing API stages recorded:

```text
PASS: 109
FAIL: 0
SKIP: 0
RESULT: PASSED
```

### Current Database / Migration Position

The current database migration head remains:

```text
008
```

Migration `008` contains the Candidate backend layer used by the current discovery workflow.

Earlier applied API migrations are historical and must not be renamed or rewritten.

---

# 3. Architecture

```text
n8n
  │ authenticated HTTP / JSON
  ▼
Marketing API (FastAPI)
  │ SQLAlchemy / psycopg
  ▼
PostgreSQL
```

Dashboard:

```text
Browser
  │
  ▼
Dashboard / BFF
  │ X-API-Key
  ▼
Marketing API
  ▼
PostgreSQL
```

### Hard Rules

```text
n8n       → Marketing API ✓
n8n       → PostgreSQL    ✕

Dashboard → Marketing API ✓
Dashboard → PostgreSQL    ✕

Browser   → PostgreSQL    ✕
Browser   → API Secret    ✕

Marketing API → PostgreSQL ✓
```

---

# 4. Running Services

```text
lorrysystem-postgres
lorrysystem-marketing-api
n8n
n8n-cloudflared
lorrysystem-dashboard
```

### Docker Networks

```text
lorrysystem-marketing-api
├── lorrysystem-api-net
└── lorrysystem-db-net

lorrysystem-postgres
└── lorrysystem-db-net

n8n
├── lorrysystem-api-net
└── n8n_default

n8n-cloudflared
└── n8n_default

lorrysystem-dashboard
├── dashboard_default
└── lorrysystem-api-net
```

---

# 5. Candidate Backend — COMPLETE

Migration `008` is applied.

### Tables

```text
lead_candidates
lead_candidate_sources
```

### Candidate Statuses

```text
NEW
READY_FOR_REVIEW
NEEDS_REVIEW
ACCEPTED
REJECTED
DUPLICATE
FAILED
```

### Candidate Source Types

```text
SEARCH_RESULT
COMPANY_WEBSITE
PUBLIC_DIRECTORY
NEWS
RSS
PUBLIC_PAGE
```

### Candidate API

```text
GET    /api/candidates
POST   /api/candidates

GET    /api/candidates/{candidate_id}
PATCH  /api/candidates/{candidate_id}

POST   /api/candidates/{candidate_id}/sources
POST   /api/candidates/{candidate_id}/accept
POST   /api/candidates/{candidate_id}/reject
```

### Candidate Backend Validation

```text
PASS: 102
FAIL: 0
SKIP: 0
RESULT: PASSED
```

### Important Candidate API Behaviour

```text
NEW_CANDIDATE
EXISTING_COMPANY
EXISTING_ACTIVE_LEAD
EXISTING_CANDIDATE
```

The API handles deduplication centrally.

n8n must NOT query PostgreSQL directly for deduplication.

---

# 6. Dashboard — COMPLETE

### Routes

```text
GET  /discovered-leads
GET  /discovered-leads/{candidate_id}

POST /discovered-leads/{candidate_id}/edit
POST /discovered-leads/{candidate_id}/accept
POST /discovered-leads/{candidate_id}/reject
```

### Dashboard Features

- [x] Reviewable candidate list
- [x] READY_FOR_REVIEW filter
- [x] NEEDS_REVIEW filter
- [x] Accepted filter
- [x] Rejected filter
- [x] Duplicate filter
- [x] Failed filter
- [x] Search
- [x] Candidate details
- [x] Suggested ICP
- [x] Confidence
- [x] Company / contact information
- [x] Fleet evidence
- [x] Buying signals
- [x] Source evidence
- [x] Accept
- [x] Edit
- [x] Reject

Dashboard regression:

```text
PASS: 54
FAIL: 0
SKIP: 0
RESULT: PASSED
```

---

# 7. Level 1 Web Discovery — IMPLEMENTED

Current flow:

```text
Manual Trigger
→ Discovery Inputs
→ Brave Search
→ Normalize & Filter URLs
→ Fetch Public Website
→ Classify Fetch Result
→ Successful Fetch?
→ HTML → Clean Text
→ Cheap Relevance Gate
→ Relevant?
→ OpenAI Structured Extraction
→ Validate AI Extraction
→ AI Extraction OK?
→ OpenAI ICP Evaluation
→ Validate ICP Evaluation
→ ICP Evaluation OK?
→ Candidate Eligible?
→ Build Candidate Payload
→ Create Candidate
→ Normalize Candidate API Outcome
→ Candidate API OK?
→ Candidate Record Available?
→ Verify Candidate Detail
→ Validate Candidate Detail
→ Verify Discovered Leads Page
→ Level 1 E2E Result
```

---

# 8. Search Layer

### Search Provider

```text
Brave Search API
```

### Current Test Query

```text
haulage company Selangor Malaysia
```

### Current Test Companies

```text
UnityLink Service & Agency Sdn Bhd
Grab Haulier Sdn Bhd
Swift Haulage Berhad
LC Forwarders Sdn Bhd
```

---

# 9. Website Fetching

### Current Result

Normal HTTP fetch works for public company websites.

Fetch classifier currently distinguishes:

```text
SUCCESS
BLOCKED
BOT_PROTECTION
FAILED
```

Blocked websites will later be routed to Level 2 scraper fallback.

---

# 10. Cheap Relevance Gate

A page must have enough readable content:

```text
clean_text >= 300 characters
```

Then it passes if:

```text
strongHits >= 1
OR
relevance_score >= 6
```

### Output

```text
RELEVANT
IRRELEVANT
```

Confidence bands:

```text
HIGH
MEDIUM
LOW
```

The gate is intentionally permissive.

It is only used to avoid wasting paid AI calls on clearly irrelevant pages.

---

# 11. OpenAI Structured Extraction — COMPLETE

Hosted OpenAI model is used through the existing n8n credential.

Current model:

```text
gpt-5-mini
```

### Extracted Fields

```text
company_name
website
domain
industry
country
state
city

contact_name
job_title
email
phone
linkedin_url

fleet_clues
services
company_description
buying_signals
source_summary
```

### Rules

```text
Unknown scalar values → null
Unknown arrays        → []
No unsupported guessing
No web searching inside the model
```

---

# 12. Extraction Refinements — COMPLETE

### False Contact Protection

The workflow now rejects website credits such as:

```text
Designed by
Developed by
Website by
Powered by
SEO by
```

as company contacts.

Example fixed:

```text
Sky Rocket Digital
```

is no longer treated as a UnityLink employee.

### Fleet Evidence Classification

Fleet clues are labelled as:

```text
OWNED/OPERATED:
PARTNER NETWORK:
CAPABILITY ONLY:
OWNERSHIP UNCLEAR:
```

This prevents marketplace / platform companies from being treated as fleet owners without evidence.

---

# 13. ICP Evaluation — COMPLETE

Valid ICP codes:

```text
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
COMMERCIAL_ENTERPRISE
```

### Confidence Thresholds

```text
>= 0.90
→ STRONG

>= 0.75
→ LIKELY
→ READY_FOR_REVIEW

0.50 – 0.74
→ UNCERTAIN
→ NEEDS_REVIEW

< 0.50
→ WEAK
→ REJECTED
```

### Test Results

```text
UnityLink       → LOGISTICS_HAULAGE → 0.95
Grab Haulier    → LOGISTICS_HAULAGE → 0.85
Swift Haulage   → LOGISTICS_HAULAGE → ~0.95
LC Forwarders   → LOGISTICS_HAULAGE → 0.95
```

---

# 14. Candidate Creation — WORKING

The Candidate API is now called from n8n using:

```text
LorrySystem Marketing API
```

HTTP Header Auth credential.

### First Clean Database Run

All four companies returned:

```text
NEW_CANDIDATE
```

and:

```text
READY_FOR_REVIEW
```

### Verified

- [x] Candidate inserted
- [x] Candidate ID returned
- [x] Correct ICP
- [x] Confidence persisted
- [x] COMPANY_WEBSITE source persisted
- [x] Source URL persisted
- [x] Search query persisted
- [x] Source count = 1
- [x] Source traceability = PASS
- [x] Candidates appear in Discovered Leads dashboard
- [x] Human can Accept
- [x] Human can Reject

---

# 15. Source Traceability — WORKING

Minimum source evidence preserved:

```text
source_type
url
title
source_query
summary
evidence
discovered_at
```

For Level 1 discovery, the inspected company page is stored as:

```text
COMPANY_WEBSITE
```

or:

```text
PUBLIC_PAGE
```

Search metadata from Brave is retained within the source evidence.

The initial source is NOT `SEARCH_RESULT` only.

---

# 16. Deduplication — WORKING

The backend checks:

```text
existing Companies
existing active Leads
existing Lead Candidates
```

Potential outcomes:

```text
NEW_CANDIDATE
EXISTING_COMPANY
EXISTING_ACTIVE_LEAD
EXISTING_CANDIDATE
```

A second run does not create duplicate candidates.

---

# 17. Clean Database Retest — COMPLETE

Before the clean Level 1 insertion test, all runtime/business data was cleared.

Preserved:

```text
alembic_version
products
icp_profiles
```

Verified seed/config state:

```text
Alembic version: 008

ICP Profiles:
COMMERCIAL_ENTERPRISE
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT

Products:
AI_DASHCAM
DMS
FUEL_MONITORING
GPS
MDVR
TMS
```

---

# 18. Level 1 E2E Validator — COMPLETE

Final workflow:

```text
lorrysystem_level1_discovery_final_validator_v5.json
```

### Final Result

```text
validator_version: level1-final-v5
overall_status: PASS
level1_freeze_ready: true
total_validated: 4

candidate_path_count: 3
existing_active_lead_path_count: 1

api_error_count: 0
failed_result_count: 0
```

### Branch Coverage

```text
EXISTING_CANDIDATE      ✓
EXISTING_ACTIVE_LEAD    ✓
```

Final branch coverage result:

```text
PASS
```

### Final Checks

```text
candidate_api                        PASS
candidate_detail                     PASS
candidate_source_traceability        PASS
dashboard_route_reachability         PASS
dashboard_ui                         VERIFIED_SEPARATELY
existing_active_lead_short_circuit   PASS
```

### Final Test Records

```text
UnityLink Service & Agency Sdn Bhd
→ EXISTING_CANDIDATE
→ PASS

Swift Haulage Berhad
→ EXISTING_CANDIDATE
→ PASS

LC Forwarders Sdn Bhd
→ EXISTING_CANDIDATE
→ PASS

Grab Haulier Sdn Bhd
→ EXISTING_ACTIVE_LEAD
→ PASS_EXISTING_ACTIVE_LEAD
```

### Validation Boundary

Automated in the final workflow:

```text
search-to-candidate pipeline
candidate API outcome
candidate detail persistence
source traceability
candidate deduplication
existing active lead short-circuit
dashboard candidate route reachability
```

Verified separately:

```text
Discovered Leads UI rendering
Accept action
Reject action
Dashboard regression suite
```

### Root Cause of Earlier False Failures

The earlier failures were validator problems, not application problems.

The previous validators attempted to verify the dashboard by scraping rendered HTML and checking for:

```text
raw candidate UUID
exact company-name rendering
specific page phrases
```

Those checks were too brittle.

The application itself had already correctly:

```text
inserted candidates
persisted sources
deduplicated candidates
shown records in Discovered Leads
allowed Accept / Reject
promoted accepted candidates into active Leads
```

Validator v5 fixed the boundary by:

```text
using the Marketing API for candidate/data verification
checking only Dashboard route reachability in n8n
keeping UI rendering and human actions as separate Dashboard tests
```

### Final Level 1 Status

```text
LEVEL 1 WEB DISCOVERY = COMPLETE
LEVEL 1 FREEZE READY  = YES
```

Do not modify the frozen Level 1 workflow unless a real regression or new requirement appears.

---

# 19. Level 1 Definition of Done

- [x] Search API works
- [x] Search results collected
- [x] URL filtering works
- [x] HTTP fetch works
- [x] Readable-text extraction works
- [x] Relevance gate works
- [x] AI extraction works
- [x] ICP evaluation works
- [x] Candidate API works
- [x] Candidate creation works
- [x] Deduplication works
- [x] Existing candidate detection works
- [x] Existing active Lead short-circuit works
- [x] Candidate source traceability works
- [x] Candidate detail persistence works
- [x] Candidate appears in Dashboard
- [x] Dashboard candidate route reachable
- [x] Accept works
- [x] Reject works
- [x] Final E2E validator returns PASS
- [x] Level 1 freeze readiness confirmed

```text
LEVEL 1 STATUS: COMPLETE
```

---

# 20. Next Stage — Level 2 Scraper Fallback

Level 2 must only run when Level 1 normal fetching fails.

### Trigger Examples

```text
403 bot protection
JavaScript-rendered content
Empty HTML
Anti-bot interstitial
Insufficient readable content
```

### Intended Flow

```text
Normal HTTP Fetch
        ↓
     Failure
        ↓
Level 2 Scraper / Browser
        ↓
Rendered Content
        ↓
Same Clean Text
        ↓
Same AI Extraction
        ↓
Same ICP Evaluation
        ↓
Same Candidate API
```

### Rules

- [ ] Do not bypass login
- [ ] Do not bypass CAPTCHA
- [ ] Do not access private pages
- [ ] Do not create a separate candidate pipeline
- [ ] Reuse existing deduplication
- [ ] Reuse existing source traceability
- [ ] Reuse existing human review

---

# 21. Level 3 — Controlled Social Discovery

Only start after Level 2 is stable.

Preferred order:

```text
1. Official social APIs
2. Approved third-party providers
3. Public/search-indexed company pages
```

Do NOT implement:

```text
private profile scraping
login bypass
CAPTCHA bypass
mass LinkedIn member scraping
unrestricted social harvesting
```

Potential evidence:

```text
fleet expansion
driver hiring
new depots
new branches
vehicle purchases
new contracts
digitisation signals
safety activity
```

---

# 22. Security / Cleanup Tasks

- [ ] Rotate Marketing API key after implementation cleanup
- [ ] Update n8n `LorrySystem Marketing API` credential after rotation
- [ ] Rotate Dashboard session secret
- [ ] Archive/remove old patch backup folders
- [ ] Strengthen SSRF protection before unattended scheduling
- [ ] Add retry logic:
  - timeout retry max 2
  - respect 429 Retry-After
  - avoid aggressive 403 retries
- [ ] Consider better footer/contact retention before 20k text clipping
- [ ] Preserve validator scripts in `/opt/lorrysystem-marketing/api/scripts`

---

# 23. Current Recommended Next Actions

```text
1. Freeze Level 1 workflow
2. Keep validator v5 as the final Level 1 regression workflow
3. Start Level 2 scraper fallback design
4. Route only BLOCKED / BOT_PROTECTION / FAILED / insufficient-content URLs to Level 2
5. Reuse the same Clean Text → AI Extraction → ICP → Candidate API path
6. Add controlled retry rules
7. Add scraper fallback source traceability
8. Validate Level 2
9. Test Passenger Transport ICP
10. Test Commercial Enterprise ICP
11. Add negative-control discovery tests
12. Begin Level 3 controlled social discovery only after Level 2 is stable
```

---

# 24. MVP1 Lead Discovery Progress Snapshot

```text
Business Card Intake             COMPLETE
CSV Intake                       COMPLETE
Candidate Backend                COMPLETE
Candidate Dashboard              COMPLETE

Level 1 Search                   COMPLETE
Level 1 Fetch                    COMPLETE
Level 1 AI Extraction            COMPLETE
Level 1 ICP Evaluation           COMPLETE
Level 1 Candidate Creation       COMPLETE
Level 1 Source Traceability      COMPLETE
Level 1 Deduplication            COMPLETE
Level 1 Dashboard Review         COMPLETE
Level 1 Existing Lead Handling   COMPLETE
Level 1 Final E2E Validator      PASS
Level 1 Freeze Ready             YES

Core Marketing API
├── Research API                 COMPLETE
├── Scoring API                  COMPLETE
├── Product Matching API         COMPLETE
├── Marketing Actions API        COMPLETE
└── Approval API                 COMPLETE

Level 2 Scraper Fallback         NOT STARTED
Level 3 Social Discovery         NOT STARTED
Final Lead Discovery Regression  NOT STARTED
```

---

## Current Milestone

**Level 1 Web Discovery is officially complete and freeze-ready.**

The supporting Marketing API business layers through Approval are also complete and validated. The discovery roadmap now continues with Level 2 only; do not reopen frozen Level 1 or completed API modules unless a real regression or new requirement appears.

Final validator:

```text
level1-final-v5
overall_status: PASS
level1_freeze_ready: true
```

Next milestone:

```text
LEVEL 2 — SCRAPER FALLBACK
```

Level 2 must only handle URLs that normal Level 1 fetching cannot process successfully.
