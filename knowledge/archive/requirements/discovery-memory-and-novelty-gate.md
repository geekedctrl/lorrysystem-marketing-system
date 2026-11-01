---
title: LorrySystem MVP1 Level 1.1 — Discovery Memory / Novelty Gate Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
date: 2026-09-27
status: ready-to-build
scope: Level 1 Update
storage: n8n Data Table
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.


# LorrySystem MVP1 Level 1.1 — Discovery Memory / Novelty Gate Handoff

## 1. Purpose

Level 1 Web Discovery is already complete and freeze-ready.

This update does **not** replace the working Level 1 pipeline.

It adds a lightweight **Discovery Memory / Novelty Gate** early in the workflow so n8n does not keep processing the same companies repeatedly.

The problem being solved is:

```text
Brave Search
    ↓
returns the same companies again
    ↓
website fetch
    ↓
AI extraction
    ↓
ICP evaluation
    ↓
Candidate API
    ↓
backend says:
"already exists"
```

The backend already prevents duplicate Leads/Candidates, but the system still wastes:

```text
search-result slots
website fetches
AI calls
time
API credits
processing capacity
```

This update moves duplicate awareness to the **front of Level 1**.

---

# 2. Storage Decision

The Discovery Memory will live inside:

```text
n8n Data Tables
```

NOT PostgreSQL.

Reason:

```text
fast local lookup
simple implementation
low overhead
close to the workflow
no additional Marketing API endpoint needed
no DB migration required
```

This table is only workflow memory.

It does NOT replace:

```text
Companies
Contacts
Leads
Lead Candidates
Candidate Sources
```

Those remain authoritative in PostgreSQL through the Marketing API.

---

# 3. Architecture

Current Level 1:

```text
Brave Search
    ↓
Normalize & Filter URLs
    ↓
Fetch Public Website
    ↓
Classify Fetch
    ↓
Clean Text
    ↓
Relevance Gate
    ↓
AI Extraction
    ↓
ICP Evaluation
    ↓
Candidate API
```

Updated Level 1.1:

```text
Brave Search
    ↓
Normalize & Filter URLs
    ↓
NEW: Discovery Memory Gate
    ↓
Already Seen?
 ┌───────┴────────┐
 YES               NO
  │                 │
Skip result      Reserve Record
  │                 │
Get next result     ↓
  │             Fetch Website
  │                 ↓
  └────────────→ Existing Level 1
```

The new gate must sit:

```text
AFTER:
Normalize & Filter URLs

BEFORE:
Fetch Public Website
```

---

# 4. n8n Data Table

Recommended table name:

```text
lead_discovery_registry
```

This table stores lightweight discovery history.

---

# 5. Recommended Columns

Suggested columns:

```text
id
canonical_domain
canonical_url
company_name

status

first_seen_at
last_seen_at
times_seen

first_source_query
last_source_query
search_provider

candidate_id
company_id
lead_id

last_failure_reason
retry_after

created_at
updated_at
```

Minimum practical fields for MVP1:

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

# 6. Primary Matching Key

Preferred lookup order:

```text
1. canonical_domain
2. canonical_url
3. normalized company name if available
```

Domain should normally be strongest.

Examples:

```text
https://www.example.com/
https://example.com/about
http://example.com/contact
```

should all normalize to:

```text
example.com
```

This prevents one company from being treated as multiple discoveries.

---

# 7. URL / Domain Normalisation

Before checking the Data Table:

```text
lowercase hostname
remove www.
remove URL fragment
remove obvious tracking parameters
remove trailing slash where appropriate
extract root/canonical domain
```

Example:

```text
https://www.swiftlogistics.com/about?utm_source=brave
```

becomes:

```text
canonical_domain:
swiftlogistics.com

canonical_url:
https://swiftlogistics.com/about
```

Do not aggressively rewrite paths unless safe.

---

# 8. Suggested Statuses

Use meaningful status values rather than only `seen=true`.

Recommended:

```text
SEEN
FETCHED
CANDIDATE_CREATED
EXISTING_CANDIDATE
EXISTING_ACTIVE_LEAD
IRRELEVANT
FETCH_FAILED
BOT_PROTECTION
BLOCKED
LEVEL2_REQUIRED
REJECTED
```

Optional:

```text
PROCESSING
RETRY_LATER
```

---

# 9. Why Status Matters

Example:

```text
swiftlogistics.com
status = EXISTING_CANDIDATE
```

means:

```text
skip future Level 1 processing
```

Example:

```text
abc-haulage.com
status = LEVEL2_REQUIRED
```

means:

```text
do NOT retry normal Level 1 fetch repeatedly
send it to Level 2 later
```

Example:

```text
exampletransport.com
status = FETCH_FAILED
retry_after = 2026-10-04
```

means:

```text
skip until retry date
```

---

# 10. Early Discovery Gate Logic

For every normalized Brave Search result:

```text
Search Result
    ↓
Normalize Domain/URL
    ↓
Lookup n8n Data Table
    ↓
Existing Record?
```

If NO:

```text
insert discovery record
status = SEEN
times_seen = 1
continue to Level 1 fetch
```

If YES:

```text
increment times_seen
update last_seen_at
update last_source_query
evaluate existing status
```

---

# 11. Skip Rules

Recommended default skip statuses:

```text
CANDIDATE_CREATED
EXISTING_CANDIDATE
EXISTING_ACTIVE_LEAD
REJECTED
```

These should normally return:

```text
PROCESS = false
```

and n8n moves to the next search result.

---

# 12. Retry Rules

Recommended:

```text
FETCH_FAILED
→ retry only after retry_after

BOT_PROTECTION
→ mark LEVEL2_REQUIRED

BLOCKED
→ mark LEVEL2_REQUIRED

LEVEL2_REQUIRED
→ skip Level 1
→ Level 2 queue later

IRRELEVANT
→ optional cooldown before rediscovery
```

For MVP1, an easy rule for irrelevant companies:

```text
retry_after = 90 days later
```

This avoids permanently blacklisting a company that may change later.

---

# 13. Reserve Before Processing

When a new company is found, insert it into the Data Table **before** fetching.

Recommended:

```text
status = SEEN
```

or:

```text
status = PROCESSING
```

This reduces duplicate processing when multiple branches/runs see the same domain.

Example:

```text
Workflow A sees example.com
→ inserts PROCESSING

Workflow B sees example.com seconds later
→ finds existing record
→ skips
```

---

# 14. Important Concurrency Note

n8n Data Tables are fast and convenient, but this is not the same as a strongly transactional PostgreSQL uniqueness constraint.

Therefore:

```text
do not run many parallel discovery workflows against the same search space initially
```

Recommended MVP1 approach:

```text
one Level 1 discovery run at a time
or
low concurrency
```

The Marketing API still remains the final authoritative deduplication layer.

So:

```text
n8n Data Table
= early efficiency filter

Marketing API
= final deduplication authority
```

---

# 15. Updated Level 1 Flow

Recommended full flow:

```text
Manual / Scheduled Trigger
        ↓
Discovery Inputs
        ↓
Brave Search
        ↓
Normalize & Filter URLs
        ↓
Normalize Domain
        ↓
Discovery Registry Lookup
        ↓
Already Processed?
   ┌────────────┴────────────┐
  YES                        NO
   │                          │
Update last_seen         Insert/Reserve
   │                          │
Skip result                   ↓
   │                     Fetch Public Website
   │                          ↓
   │                     Classify Fetch Result
   │                          ↓
   │                     Successful?
   │                     ┌─────┴─────┐
   │                    YES          NO
   │                     │            │
   │                     │       Update Registry
   │                     │       LEVEL2_REQUIRED /
   │                     │       FETCH_FAILED
   │                     │
   │                     ↓
   │                HTML → Clean Text
   │                     ↓
   │                Relevance Gate
   │                     ↓
   │                Relevant?
   │               ┌─────┴─────┐
   │              YES          NO
   │               │            │
   │               │      Update Registry
   │               │      IRRELEVANT
   │               ↓
   │        OpenAI Extraction
   │               ↓
   │        ICP Evaluation
   │               ↓
   │        Candidate Eligible?
   │               ↓
   │        Candidate API
   │               ↓
   │        Normalize API Result
   │               ↓
   │        Update Registry
   │
   └────────→ Continue Search
```

---

# 16. Search for NEW Companies, Not Just Results

The workflow should not stop simply because Brave returned N results.

Instead define:

```text
TARGET_NEW_COMPANIES
```

Example:

```text
TARGET_NEW_COMPANIES = 10
```

Then:

```text
Brave returns 10 results
7 already seen
3 new

new_count = 3

Need 7 more
→ fetch next search result page / query variation
```

---

# 17. Recommended Loop Logic

Conceptual:

```text
new_companies_found = 0
results_scanned = 0

WHILE:
new_companies_found < TARGET_NEW_COMPANIES
AND results_scanned < MAX_RESULTS_SCANNED
AND query_count < MAX_QUERY_VARIANTS

    search
    normalize
    check discovery registry

    if seen:
        skip

    if unseen:
        reserve
        new_companies_found += 1
        process
```

---

# 18. Safety Limits

Never let the workflow search forever.

Recommended initial values:

```text
TARGET_NEW_COMPANIES = 10

MAX_RESULTS_SCANNED = 100

MAX_QUERY_VARIANTS = 10

MAX_RUNTIME_MINUTES = 20
```

These values can be adjusted after real usage.

---

# 19. Search Exhaustion Behaviour

Example:

```text
Target:
10 new companies

Maximum results scanned:
100

Found:
6 new companies

Result:
finish successfully with 6
```

Do NOT:

```text
keep searching forever
```

Return a summary:

```text
target_new_companies: 10
new_companies_found: 6
results_scanned: 100
search_exhausted: true
```

---

# 20. Registry Update After Fetch

After normal website fetch:

```text
SUCCESS
→ status = FETCHED
```

If:

```text
BOT_PROTECTION
→ status = LEVEL2_REQUIRED
last_failure_reason = BOT_PROTECTION
```

If:

```text
BLOCKED
→ status = LEVEL2_REQUIRED
last_failure_reason = BLOCKED
```

If:

```text
FAILED
→ status = FETCH_FAILED
last_failure_reason = <reason>
retry_after = <future date>
```

---

# 21. Registry Update After Relevance Gate

If clearly irrelevant:

```text
status = IRRELEVANT
retry_after = +90 days
```

---

# 22. Registry Update After Candidate API

If API returns:

```text
NEW_CANDIDATE
```

update:

```text
status = CANDIDATE_CREATED
candidate_id = <id>
```

If:

```text
EXISTING_CANDIDATE
```

update:

```text
status = EXISTING_CANDIDATE
candidate_id = <id>
```

If:

```text
EXISTING_ACTIVE_LEAD
```

update:

```text
status = EXISTING_ACTIVE_LEAD
lead_id = <id if returned>
```

If:

```text
EXISTING_COMPANY
```

store:

```text
company_id = <id if available>
```

and continue according to existing Candidate API behavior.

---

# 23. Level 2 Queue Preparation

This update should prepare Level 2 automatically.

Any record with:

```text
status = LEVEL2_REQUIRED
```

becomes eligible for ZenRows later.

Future Level 2 flow:

```text
n8n Data Table
    ↓
Filter:
status = LEVEL2_REQUIRED
    ↓
ZenRows
    ↓
Rendered Page
    ↓
Existing Clean Text
    ↓
Existing AI Extraction
    ↓
Existing ICP Evaluation
    ↓
Existing Candidate API
```

This means Level 2 does not need a separate queue/database.

---

# 24. Suggested Level 2 Fields

The same Data Table may later add:

```text
level2_attempted_at
level2_provider
level2_result
level2_credits_used
level2_retry_after
```

Do not add these until Level 2 implementation if not needed yet.

---

# 25. Data Table Responsibilities

The n8n Data Table handles:

```text
seen-domain memory
seen-URL memory
search novelty
early skip decisions
Level 2 routing status
retry timing
workflow efficiency
```

It does NOT handle:

```text
authoritative company records
authoritative Leads
authoritative Candidates
approval history
contact data ownership
marketing actions
```

---

# 26. PostgreSQL / Marketing API Still Authoritative

Final duplicate prevention remains:

```text
n8n
    ↓
Candidate API
    ↓
Marketing API
    ↓
PostgreSQL
```

The Marketing API should continue handling:

```text
EXISTING_COMPANY
EXISTING_ACTIVE_LEAD
EXISTING_CANDIDATE
NEW_CANDIDATE
```

Do not remove backend deduplication.

The Discovery Registry only prevents unnecessary work earlier.

---

# 27. Failure Recovery

If n8n Data Table data is lost:

```text
Level 1 still works
```

because the Marketing API still prevents duplicate business records.

The result would only be:

```text
more repeated searches
more repeated fetches
more AI usage
```

not corrupted Lead data.

This is intentional.

The table should be treated as:

```text
workflow optimisation state
```

not critical business truth.

---

# 28. Backup

Even though the table is not authoritative, periodically export/backup it.

Recommended:

```text
daily or weekly export
```

or include it in n8n backup procedures.

---

# 29. Suggested n8n Nodes

Possible section:

```text
Normalize Search Result
        ↓
Normalize Domain
        ↓
Data Table: Get Row
        ↓
IF Existing?
   ├── YES
   │    ↓
   │ Data Table: Update
   │    ↓
   │ Skip
   │
   └── NO
        ↓
     Data Table: Insert
        ↓
     Existing Level 1 Fetch
```

Exact Data Table actions depend on the current n8n version.

---

# 30. Recommended n8n Workflow Sections

Use clear labels:

```text
A — Search
B — Normalize
C — Discovery Memory Gate
D — Level 1 Fetch
E — Fetch Classification
F — Clean Text
G — Relevance Gate
H — AI Extraction
I — ICP Evaluation
J — Candidate API
K — Discovery Registry Update
L — Run Summary
```

---

# 31. Run Summary

At the end of every discovery run, return:

```text
search_results_scanned
existing_registry_hits
new_domains_found
websites_fetched
irrelevant_pages
candidates_created
existing_candidates
existing_active_leads
level2_required
fetch_failed
```

Example:

```json
{
  "search_results_scanned": 50,
  "existing_registry_hits": 31,
  "new_domains_found": 19,
  "websites_fetched": 19,
  "irrelevant_pages": 5,
  "candidates_created": 8,
  "existing_candidates": 2,
  "existing_active_leads": 1,
  "level2_required": 3,
  "fetch_failed": 0
}
```

---

# 32. Validation Scenarios

Test at least:

```text
1. Brand-new domain
2. Same domain on second run
3. Different URL from same domain
4. Existing Candidate
5. Existing Active Lead
6. Irrelevant company
7. BOT_PROTECTION
8. BLOCKED
9. FETCH_FAILED
10. Retry-after behavior
11. Target-new-company loop
12. Search exhaustion
```

---

# 33. Expected Results

### Test 1 — New Domain

```text
Registry miss
→ insert
→ process Level 1
```

### Test 2 — Same Domain

```text
Registry hit
→ skip before fetch
```

### Test 3 — Different URL / Same Domain

```text
canonical domain matches
→ skip
```

### Test 4 — Bot Protection

```text
Level 1 fails
→ status = LEVEL2_REQUIRED
```

### Test 5 — Existing Candidate

```text
Candidate API says EXISTING_CANDIDATE
→ registry updated
→ future discovery skips early
```

---

# 34. Level 1.1 Definition of Done

```text
n8n Data Table created                         ✓
domain normalisation implemented              ✓
URL normalisation implemented                 ✓
early registry lookup implemented             ✓
new domains reserved before fetch             ✓
seen domains skipped before fetch             ✓
times_seen tracking works                     ✓
last_seen tracking works                      ✓
fetch results update registry                 ✓
candidate API results update registry         ✓
LEVEL2_REQUIRED routing state works           ✓
retry-after logic works                       ✓
target-new-company loop works                 ✓
max-search safety limit works                 ✓
run summary works                             ✓
existing Level 1 downstream still passes      ✓
backend dedup remains unchanged               ✓
```

---

# 35. Important Rule — Do Not Break Frozen Level 1

Level 1 downstream is already validated.

Do NOT rewrite:

```text
Clean Text
Relevance Gate
OpenAI Extraction
ICP Evaluation
Candidate API
Source Traceability
Dashboard Review
```

The new logic should be inserted only around the early search/fetch stage and final registry update stage.

Preferred:

```text
Brave
↓
Normalize
↓
NEW Discovery Memory
↓
Existing frozen Level 1
```

---

# 36. Recommended Build Order

```text
1. Create n8n Data Table
2. Define fields
3. Add domain normalisation
4. Add URL normalisation
5. Add Data Table lookup
6. Add skip branch for known records
7. Add reserve/insert branch for new records
8. Update registry after fetch classification
9. Update registry after relevance result
10. Update registry after Candidate API result
11. Add LEVEL2_REQUIRED status
12. Add retry_after handling
13. Add target-new-company counter
14. Add result/query safety limits
15. Add run summary
16. Run regression against frozen Level 1
17. Freeze Level 1.1
```

---

# 37. Immediate Next Task

Start with:

```text
Create n8n Data Table:
lead_discovery_registry
```

Then add:

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

After that:

```text
insert the Discovery Memory Gate
between
Normalize & Filter URLs
and
Fetch Public Website
```

---

# 38. Final Level 1.1 Architecture

```text
                       Brave Search
                            ↓
                  Normalize / Filter
                            ↓
                Discovery Memory Gate
                    (n8n Data Table)
                            ↓
                    Already Seen?
                   ┌────────┴────────┐
                  YES                NO
                   │                  │
                 Skip              Reserve
                   │                  ↓
                   │           Level 1 Fetch
                   │                  ↓
                   │          Existing Pipeline
                   │                  ↓
                   │          Candidate API
                   │                  ↓
                   │          Registry Update
                   │
                   └─────────────→ Continue
```

This update should be completed before starting Level 2 ZenRows integration.
