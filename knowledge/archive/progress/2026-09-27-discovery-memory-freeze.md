> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

# LorrySystem MVP1 — Lead Discovery Progress Tracker

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1 — Lead Discovery  
**Date:** 27 September 2026  
**Current Status:** Level 1 + Level 1.1 completed and freeze-ready  
**Next Stage:** Level 2 Scraper Fallback

---

## 1. Current Architecture

```text
n8n
  │ authenticated HTTP/JSON
  ▼
Marketing API (FastAPI)
  │ SQLAlchemy / psycopg
  ▼
PostgreSQL
```

Dashboard:

```text
Browser
  │ HTTP / HTTPS
  ▼
Dashboard / BFF
  │ server-side X-API-Key
  ▼
Marketing API
  ▼
PostgreSQL
```

Security boundaries remain:

```text
n8n       → Marketing API ✓
n8n       → PostgreSQL    ✕

Dashboard → Marketing API ✓
Dashboard → PostgreSQL    ✕

Browser   → PostgreSQL    ✕
Browser   → API secret    ✕

Marketing API → PostgreSQL ✓
```

---

# 2. Completed Backend Foundation

## Marketing API

Completed and validated:

- Companies API
- Contacts API
- Leads API
- Research API
- Scoring API
- Product Matching API
- Marketing Actions API
- Approval API
- Candidate Discovery staging API
- Candidate source traceability
- Candidate accept / reject flow
- Candidate → Lead conversion
- Existing Company reuse
- Existing active Lead short-circuit
- Candidate deduplication
- Database integrity checks

Current Alembic head:

```text
008
```

Candidate tables:

```text
lead_candidates
lead_candidate_sources
```

Candidate statuses:

```text
NEW
READY_FOR_REVIEW
NEEDS_REVIEW
ACCEPTED
REJECTED
DUPLICATE
FAILED
```

Candidate API backend validator:

```text
PASS: 102
FAIL: 0
SKIP: 0
RESULT: PASSED
```

Full backend regression:

```text
PASS: 94
FAIL: 0
SKIP: 5
RESULT: PASSED
```

---

# 3. Discovered Leads Dashboard

Completed:

```text
GET  /discovered-leads
GET  /discovered-leads/{candidate_id}
POST /discovered-leads/{candidate_id}/edit
POST /discovered-leads/{candidate_id}/accept
POST /discovered-leads/{candidate_id}/reject
```

Dashboard supports:

- Review queue
- READY_FOR_REVIEW
- NEEDS_REVIEW
- ACCEPTED
- REJECTED
- DUPLICATE
- FAILED
- ALL
- Company details
- Contact details
- ICP suggestion
- ICP confidence
- ICP reasoning
- Fleet clues
- Buying signals
- Source evidence
- Edit / accept / reject

Dashboard regression:

```text
PASS: 54
FAIL: 0
SKIP: 0
RESULT: PASSED
```

Human acceptance flow verified with Grab Haulier.

---

# 4. Level 1 — Web Discovery

## Status

```text
LEVEL 1
STATUS: COMPLETE
FREEZE READY: YES
```

Final Level 1 pipeline:

```text
ICP Search Query
→ Brave Search API
→ Search Results
→ URL Filtering
→ HTTP Fetch
→ HTML → Clean Text
→ Cheap Relevance Gate
→ OpenAI Structured Extraction + ICP Evaluation
→ Candidate Eligibility
→ Candidate API
→ Candidate Detail Verification
→ Dashboard Route Verification
```

Level 1 extraction captures:

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
suggested_icp
icp_confidence
icp_reasoning
```

Supported ICPs:

```text
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
COMMERCIAL_ENTERPRISE
```

Confidence rules:

```text
>= 0.90  STRONG
>= 0.75  LIKELY
>= 0.50  UNCERTAIN
<  0.50  WEAK
```

Candidate threshold:

```text
>= 0.75  READY_FOR_REVIEW
>= 0.50  NEEDS_REVIEW
<  0.50  REJECTED
```

Final Level 1 validator:

```text
validator_version: level1-final-v5
overall_status: PASS
level1_freeze_ready: true
```

Validated:

- Search-to-candidate pipeline
- Candidate API outcome
- Candidate detail persistence
- Source traceability
- Candidate deduplication
- Existing active Lead short-circuit
- Dashboard route reachability

---

# 5. Level 1.1 — Discovery Memory / Novelty Gate

## Status

```text
LEVEL 1.1
STATUS: COMPLETE
FREEZE READY: YES
```

Purpose:

Prevent repeated Brave results from wasting:

- Search result slots
- Website fetches
- OpenAI calls
- Candidate API calls
- Processing time
- API credits

Storage:

```text
n8n Data Table
```

Table:

```text
lead_discovery_registry
```

The Data Table is workflow memory only.

Authoritative business data remains:

```text
Marketing API
→ PostgreSQL
```

---

## 5.1 Discovery Registry Fields

```text
canonical_domain
canonical_url
status
first_seen_at
last_seen_at
times_seen
last_source_query
search_provider
candidate_id
lead_id
last_failure_reason
retry_after
```

---

## 5.2 Registry Statuses

Current status lifecycle:

```text
PROCESSING
FETCHED
CANDIDATE_CREATED
EXISTING_CANDIDATE
EXISTING_ACTIVE_LEAD
IRRELEVANT
FETCH_FAILED
LEVEL2_REQUIRED
REJECTED
RETRY_LATER
```

Default permanent skip statuses:

```text
CANDIDATE_CREATED
EXISTING_CANDIDATE
EXISTING_ACTIVE_LEAD
REJECTED
LEVEL2_REQUIRED
BOT_PROTECTION
BLOCKED
```

Retry behavior:

```text
FETCH_FAILED
→ retry after 7 days

IRRELEVANT
→ retry after 90 days

RETRY_LATER
→ retry after 1 day
```

---

# 6. Level 1.1 Early Novelty Gate

The registry gate is placed before website fetching.

```text
Brave Search
→ Normalize & Filter URLs
→ Normalize Discovery Key
→ Registry Lookup
```

Existing discovery:

```text
Registry Row Exists?
→ Get Existing Registry Row
→ Prepare Existing Registry Decision
→ Reprocess Existing?
```

If allowed to retry:

```text
TRUE
→ Update Registry Reprocess
→ Restore Existing Discovery Context
→ Fetch Public Website
```

If already known / final:

```text
FALSE
→ Update Registry Skip
→ Registry Skip Result
→ Level 1.1 Skip Validation Summary
```

New discovery:

```text
Registry Row Missing
→ Limit New Companies
→ Prepare New Registry Record
→ Reserve New Discovery
→ Restore New Discovery Context
→ Fetch Public Website
```

---

# 7. Brave Search Pagination

Brave Search currently uses:

```text
brave_count = 20
max_results_scanned = 40
target_new_companies = 10
```

Brave API requests are throttled:

```text
Batch Size: 1
Batch Interval: 1500 ms
```

This avoids Brave free-plan rate-limit errors.

Current pagination:

```text
offset 0
offset 1
```

Maximum search results scanned:

```text
40
```

The Discovery Memory gate allows Brave to search deeper while already-known companies are skipped.

---

# 8. AI Optimization

Previous Level 1 flow used two OpenAI calls per company:

```text
Structured Extraction
→ ICP Evaluation
```

Optimized flow now uses one combined call:

```text
Structured Extraction + ICP Evaluation
```

Current model:

```text
gpt-5-mini
```

Maximum AI website text:

```text
10,000 characters
```

Composition:

```text
7,000 chars from page beginning
3,000 chars from page footer / end
```

Structured data cap:

```text
3,000 characters
```

This reduced AI latency and token usage while preserving:

- Company identity
- Contact data
- Fleet clues
- Buying signals
- ICP classification
- ICP confidence
- ICP reasoning

---

# 9. Directory / Aggregator Safety

A directory-domain issue was identified and fixed.

Problem example:

```text
Company:
LOAD N GO SDN BHD

Source:
freightnet.com
```

Old risk:

```text
freightnet.com
→ incorrectly treated as company's own domain
```

Fixed behavior:

For normal company websites:

```text
https://www.ktlog.com.my/services
https://ktlog.com.my/about

→ registry key:
https://ktlog.com.my/
```

For directories / aggregators:

```text
freightnet.com
businesslist.my
goodfirms.co
zoominfo.com
```

Registry memory is URL-scoped:

```text
https://freightnet.com/directory/p1/cMY/s25.htm
```

rather than blocking the entire directory domain.

AI rule:

```text
If directory_source = true,
the directory domain must NOT become the target company's own domain.
```

If no separate company website is supported:

```json
{
  "website": null,
  "domain": null
}
```

Validated example:

```text
LOAD N GO SDN BHD
domain: null
is_directory_source: true
candidate_outcome: NEW_CANDIDATE
candidate_detail_verification: PASS
source_traceability: PASS
directory_domain_safety: PASS
```

---

# 10. Registry Final Lifecycle Updates

Registry records are now updated after each major stage.

After fetch:

```text
SUCCESS
→ FETCHED

BLOCKED / BOT PROTECTION
→ LEVEL2_REQUIRED

FAILED
→ FETCH_FAILED
```

After relevance:

```text
Relevant
→ FETCHED

Irrelevant
→ IRRELEVANT
```

After AI:

```text
AI failure
→ RETRY_LATER
```

After ICP eligibility:

```text
Below threshold
→ REJECTED
```

After Candidate API:

```text
NEW_CANDIDATE
→ CANDIDATE_CREATED
→ candidate_id saved

EXISTING_COMPANY
→ CANDIDATE_CREATED
→ candidate_id saved

EXISTING_CANDIDATE
→ EXISTING_CANDIDATE
→ candidate_id saved

EXISTING_ACTIVE_LEAD
→ EXISTING_ACTIVE_LEAD
→ lead_id saved
```

The workflow reads the Data Table row back and verifies that the persisted registry status and ID match the Candidate API result.

---

# 11. Level 1.1 Processed-Path Validator

Current validator:

```text
validator_version: level1.1-final-v2
```

Latest processed-path result:

```text
overall_status: PASS
level1_freeze_ready: true
level1_1_processed_path_validation: PASS
```

Checks:

```text
candidate_api                    PASS
candidate_detail                 PASS
candidate_source_traceability    PASS
dashboard_route_reachability     PASS
discovery_registry_final_state   PASS
directory_domain_safety          PASS
```

The validator no longer requires the existing-active-lead Candidate API branch to execute on every run because Discovery Memory may correctly intercept known active Leads before Candidate API.

---

# 12. Level 1.1 Skip Validator

Final novelty-gate validator:

```text
validator_version: level1.1-skip-v1
```

Final result:

```text
overall_status: PASS
level1_1_freeze_ready: true
```

Final skip statistics:

```text
skipped_before_fetch:        30
website_fetches_avoided:     30
ai_calls_avoided:            30
candidate_api_calls_avoided: 30
failed_skip_checks:          0
```

Registry statuses observed in the validation run:

```text
EXISTING_CANDIDATE      7
EXISTING_ACTIVE_LEAD    1
FETCH_FAILED            4
CANDIDATE_CREATED      14
IRRELEVANT              1
LEVEL2_REQUIRED         3
```

This proves that already-known discovery results are stopped before:

```text
Website Fetch
OpenAI
Candidate API
```

---

# 13. Level 1.1 Definition of Done

| Requirement | Status |
|---|---|
| n8n Data Table registry exists | ✅ |
| Registry lookup before website fetch | ✅ |
| Canonical URL/domain normalization | ✅ |
| Existing-result skip logic | ✅ |
| Retry-aware reprocessing | ✅ |
| New discovery reservation | ✅ |
| Target-new-company limit | ✅ |
| Brave pagination | ✅ |
| Brave rate limiting | ✅ |
| Registry lifecycle updates | ✅ |
| Candidate ID persistence | ✅ |
| Lead ID persistence | ✅ |
| Directory / aggregator handling | ✅ |
| Directory-domain leakage protection | ✅ |
| AI call reduction | ✅ |
| Processed-path validator | ✅ |
| Skip-path validator | ✅ |
| Website fetch avoidance verified | ✅ |
| AI-call avoidance verified | ✅ |
| Candidate API avoidance verified | ✅ |
| Level 1 regression preserved | ✅ |
| Level 1.1 freeze-ready | ✅ |

---

# 14. Frozen Components

Do not modify unless a real regression or new requirement appears.

Frozen:

```text
Normalize & Filter URLs
Normalize Discovery Key
Discovery Memory Gate
Registry reservation
Registry lifecycle updates
Directory / aggregator protection
HTML → Clean Text
Cheap Relevance Gate
OpenAI Structured Extraction + ICP
Candidate Eligibility
Candidate Payload
Candidate API
Candidate detail verification
Source traceability
Dashboard route verification
Level 1 processed-path validator
Level 1.1 skip validator
```

Current production rule:

```text
DO NOT CLEAR lead_discovery_registry
```

The registry is now useful operational memory.

---

# 15. Next Stage — Level 2 Scraper Fallback

## Objective

Level 2 should only process discoveries that Level 1 could not fetch normally.

Input source:

```text
lead_discovery_registry
```

Filter:

```text
status = LEVEL2_REQUIRED
```

Current real Level 2 queue:

```text
3 records
```

Recommended Level 2 architecture:

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

Level 2 must preserve the existing downstream pipeline.

---

# 16. Level 2 Rules

Level 2 must:

- Process only `LEVEL2_REQUIRED`
- Use fallback rendering only
- Avoid CAPTCHA bypass
- Avoid login bypass
- Avoid private / restricted pages
- Preserve source traceability
- Preserve human review
- Preserve Candidate API as final dedup authority
- Preserve Marketing API → PostgreSQL architecture
- Track Level 2 provider
- Track Level 2 attempt
- Track success / failure
- Track fallback cost
- Track candidate yield
- Respect retry windows
- Avoid aggressive retry on 403
- Respect 429 / Retry-After

Planned future Level 2 fields:

```text
level2_attempted_at
level2_provider
level2_result
level2_credits_used
level2_retry_after
```

Do not add these fields until Level 2 implementation begins.

---

# 17. Remaining Later Work

After Level 2:

```text
[ ] Passenger Transport discovery test
[ ] Commercial Enterprise discovery test
[ ] Negative-control discovery tests
[ ] ICP-driven query generation
[ ] Query variation after pagination exhaustion
[ ] Better footer/contact extraction if required
[ ] SSRF hardening before unattended scheduling
[ ] Production scheduling
[ ] Marketing API key rotation
[ ] Dashboard session secret rotation
[ ] Update n8n Header Auth after key rotation
[ ] Remove old patch backup folders
[ ] Level 3 controlled social discovery
```

---

# 18. Current MVP1 Lead Discovery Status

```text
Backend Foundation        ✅ COMPLETE
Candidate API             ✅ COMPLETE
Discovered Leads UI       ✅ COMPLETE
Level 1 Web Discovery     ✅ FROZEN
Level 1 Validator         ✅ PASS
Level 1.1 Memory Gate     ✅ FROZEN
Registry Lifecycle        ✅ PASS
Directory Safety          ✅ PASS
AI Optimization           ✅ COMPLETE
Novelty Skip Validation   ✅ PASS
Level 2 Scraper Fallback  ⏳ NEXT
Level 3 Social Discovery  ⏸ LATER
```

---

# 19. Immediate Next Task

```text
Build Level 2 ZenRows Scraper Fallback
```

Start with the existing real queue:

```text
status = LEVEL2_REQUIRED
count = 3
```

Do not rewrite the frozen Level 1 / Level 1.1 downstream pipeline.

