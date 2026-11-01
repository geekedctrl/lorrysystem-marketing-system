---
title: LorrySystem MVP1 Level 1 Lead Discovery & Scraper Implementation Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
date: 2026-09-19
status: ready-to-build
scope: Level 1 Web Discovery
social_discovery: deferred
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem MVP1 Level 1 Lead Discovery & Scraper Implementation Handoff

## 1. Purpose

This document defines how **MVP1 AI Lead Discovery Level 1** should be implemented.

The agreed MVP1 discovery scope is:

```text
LEVEL 1 — Cheap / Simple

Search API
Company websites
Public directories
News
RSS
Public pages
```

Social-media discovery is NOT part of this implementation phase.

The immediate objective is:

> Use n8n to discover relevant companies on the public web, retrieve their public information, evaluate them against the LorrySystem ICP, and place qualified companies into a controlled candidate-review flow.

The discovery system must not directly create official Leads without validation and duplicate checks.

---

# 2. Position in the Overall Lead Generation Architecture

Current lead-generation sources:

```text
                    LEAD GENERATION
                          │
          ┌───────────────┼──────────────────┐
          │               │                  │
          ▼               ▼                  ▼
     Business Card        CSV           AI Discovery
          │               │                  │
          │               │                  ▼
          │               │           Level 1 Web Discovery
          │               │                  │
          └───────────────┴──────────────┬───┘
                                         ▼
                              ICP Fit / Deduplication
                                         ↓
                                  Candidate Review
                                         ↓
                              Company + Contact + Lead
                                         ↓
                                    DISCOVERED
```

Business Card and CSV flows are already implemented.

This document defines the missing **AI Discovery → Level 1 Web Discovery** path.

---

# 3. Core Architecture

n8n is the orchestrator.

It should not be treated as the search engine itself.

Recommended architecture:

```text
n8n
 │
 ├── Search API
 │
 ├── Public website fetch
 │
 ├── Public directory fetch
 │
 ├── News / RSS fetch
 │
 └── AI extraction / ICP evaluation
 │
 ▼
Lead Candidate
 │
 ▼
Dashboard Review
 │
 ▼
Marketing API
 │
 ▼
PostgreSQL
```

Hard rules:

```text
n8n        ✕ PostgreSQL
Scraper    ✕ PostgreSQL
Dashboard  ✕ PostgreSQL

n8n        ✓ Marketing API
Dashboard  ✓ Marketing API
Marketing API ✓ PostgreSQL
```

---

# 4. MVP1 Discovery Philosophy

The system should follow:

```text
Discover
   ↓
Collect public evidence
   ↓
Extract structured company data
   ↓
Evaluate ICP fit
   ↓
Check duplicates
   ↓
Create Lead Candidate
   ↓
Human review
   ↓
Promote to official Lead
```

Do not:

```text
discover company
→ immediately create lead
→ immediately contact company
```

MVP1 remains controlled automation.

---

# 5. Level 1 Source Types

The scraper/discovery workflow should support:

```text
SEARCH_RESULT
COMPANY_WEBSITE
PUBLIC_DIRECTORY
NEWS
RSS
PUBLIC_PAGE
```

Social-platform-specific discovery is deferred.

---

# 6. Search API Role

The Search API is used to discover candidate URLs.

Example search themes:

```text
haulage company Malaysia
logistics fleet Selangor
lorry transport Klang
fleet operator Malaysia
bus operator Malaysia
commercial fleet Malaysia
transport company Johor
logistics company Penang
```

Search terms should be generated from:

```text
ICP
location
industry keywords
fleet keywords
product-relevant pain points
```

Example:

```text
ICP:
LOGISTICS_HAULAGE

Possible queries:
"haulage company Selangor"
"logistics fleet Klang"
"lorry transport company Malaysia"
"container haulage Malaysia"
"fleet logistics Selangor"
```

---

# 7. Search Result Collection

For each search result, capture:

```text
title
url
snippet
source_query
position/rank if available
discovered_at
```

Do not treat the search snippet alone as enough evidence to create a candidate.

The next step must inspect the actual public page.

---

# 8. URL Filtering

Before fetching a page, reject obviously irrelevant URLs.

Examples to exclude:

```text
job boards
generic social profile pages
shopping pages
unrelated government portals
duplicate URLs
search-result cache pages
login pages
PDF spam
irrelevant directories
```

Allow:

```text
company websites
business directories
industry associations
news articles
public business pages
RSS items
```

---

# 9. Normal Website Fetch — First Attempt

For MVP1, attempt a normal HTTP fetch first.

Flow:

```text
URL
 ↓
HTTP Request
 ↓
HTML response
 ↓
Extract readable text
```

This should be the default because it is:

```text
cheap
fast
easy to operate
low maintenance
```

Do not send every page to a paid browser/scraping service automatically.

---

# 10. HTML Cleanup

After fetching:

```text
remove scripts
remove styles
remove navigation noise
remove cookie banners where practical
remove repeated headers/footers
extract readable main text
```

Retain useful content such as:

```text
About Us
Services
Fleet information
Locations
Contact details
Industries served
News
Company descriptions
```

---

# 11. Simple Scraper Success Criteria

A normal HTTP fetch is considered usable when:

```text
HTTP status is successful
content length is meaningful
page contains readable business text
content is not only JavaScript shell
content is not blocked/interstitial
```

Example success:

```text
ABC Logistics Sdn Bhd
We operate over 80 prime movers...
Services include container haulage...
Based in Port Klang...
```

---

# 12. Scraper Failure Detection

The normal scraper should detect when it failed.

Examples:

```text
403 Forbidden
429 Too Many Requests
Cloudflare challenge page
CAPTCHA
empty HTML shell
JavaScript-only application
login required
blocked robots/access response
very low text content
```

Mark these as:

```text
FETCH_FAILED
or
RENDER_REQUIRED
```

Do not keep retrying aggressively.

---

# 13. Paid / Browser Scraper Fallback

After Level 1 normal HTTP fetching is working, difficult websites may use a scraper/browser service as a fallback.

Flow:

```text
Normal HTTP Fetch
      ↓
Succeeded?
 ┌────┴────┐
 YES       NO
 │          │
Extract   Scraper/Browser API
 │          │
 └────┬─────┘
      ▼
Readable Page Content
```

Important:

> The paid scraper is a fallback, not the default path.

This controls cost.

---

# 14. When to Use the Fallback Scraper

Use fallback only when:

```text
page is JavaScript-rendered
normal fetch returns no useful content
page returns anti-bot interstitial
content clearly exists but normal fetch cannot retrieve it
```

Do not use fallback for:

```text
CAPTCHA bypass
login bypass
restricted/private pages
unrestricted social-member scraping
```

---

# 15. Public Directory Extraction

Public directories may be useful for:

```text
company name
industry
location
website
phone
business description
```

Directory data should be treated as:

```text
candidate evidence
```

not automatically trusted as authoritative.

Capture the directory URL as a source.

---

# 16. News Discovery

News can reveal:

```text
fleet expansion
new depots
new logistics contracts
new vehicle purchases
safety incidents
growth
new branches
industry activity
```

Capture:

```text
headline
publisher
url
published_at if available
relevant excerpt/summary
```

News should improve candidate context and ICP confidence.

---

# 17. RSS Support

RSS can be used for recurring discovery.

Examples:

```text
industry news feeds
transport associations
logistics publications
company news feeds
```

n8n can periodically poll RSS feeds.

Flow:

```text
RSS feed
   ↓
New item
   ↓
Relevant to ICP?
   ↓
Extract company
   ↓
Candidate enrichment
```

---

# 18. AI Extraction Layer

After readable text is collected, send the content to the AI extraction step.

The AI should extract structured fields.

Target fields:

```text
company_name
website
domain
industry
country
state
city

possible_contact_name
possible_job_title
possible_email
possible_phone
possible_linkedin_url

fleet_clues
services
company_description
buying_signals
source_summary
```

Do not hallucinate missing data.

Unknown fields should be:

```text
null
```

---

# 19. ICP Evaluation

The AI must evaluate the discovered company against current ICPs:

```text
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
COMMERCIAL_ENTERPRISE
```

Return:

```text
suggested_icp
icp_confidence
icp_reasoning
```

Example:

```json
{
  "suggested_icp": "LOGISTICS_HAULAGE",
  "icp_confidence": 0.91,
  "icp_reasoning": "Company provides container haulage services and operates a commercial truck fleet in Port Klang."
}
```

---

# 20. ICP Confidence

Recommended internal confidence scale:

```text
0.00 – 1.00
```

Example:

```text
0.90+  strong fit
0.75+  likely fit
0.50+  uncertain
<0.50  weak fit
```

Do not automatically create official leads solely based on confidence.

Confidence is for candidate prioritisation.

---

# 21. Candidate Creation Threshold

Recommended MVP1 behavior:

```text
Strong / likely ICP fit
→ create candidate

Uncertain fit
→ create candidate as NEEDS_REVIEW

Weak fit
→ discard or record as rejected discovery
```

Suggested:

```text
>= 0.75
→ READY_FOR_REVIEW

0.50–0.74
→ NEEDS_REVIEW

< 0.50
→ REJECTED_BY_DISCOVERY
```

These thresholds may be adjusted after testing.

---

# 22. Source Traceability

Every candidate must preserve evidence.

Minimum:

```text
source_type
source_url
source_title
discovered_at
source_query
```

If multiple sources support one company:

```text
Candidate
  ├── company website
  ├── directory
  └── news article
```

Do not discard source history.

---

# 23. Deduplication

Before creating a candidate:

```text
normalize domain
normalize website
normalize company name
```

Check against:

```text
existing Companies
existing active Leads
existing Lead Candidates
```

Recommended match priority:

```text
1. exact domain
2. exact normalized website
3. exact normalized company name
4. fuzzy company-name similarity
```

---

# 24. Duplicate Outcomes

Possible results:

```text
NEW_CANDIDATE
EXISTING_COMPANY
EXISTING_ACTIVE_LEAD
EXISTING_CANDIDATE
POSSIBLE_DUPLICATE
```

Behavior:

```text
EXISTING_ACTIVE_LEAD
→ do not create duplicate lead candidate

EXISTING_COMPANY
→ candidate may reference existing company

EXISTING_CANDIDATE
→ merge/enrich source evidence

POSSIBLE_DUPLICATE
→ human review
```

---

# 25. Candidate Data Model — Recommended

A new staging/candidate layer is recommended.

Conceptual fields:

```text
id
source
status

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

suggested_icp
icp_confidence
icp_reasoning

fleet_clues
buying_signals
source_summary

created_at
updated_at
reviewed_at
reviewed_by
```

Possible statuses:

```text
NEW
READY_FOR_REVIEW
NEEDS_REVIEW
ACCEPTED
REJECTED
DUPLICATE
FAILED
```

Do not implement schema blindly.

Inspect the existing database first.

If a new table is required, use the next real migration ID.

---

# 26. Candidate Sources — Recommended Structure

Prefer storing multiple sources per candidate.

Conceptual:

```text
lead_candidate_sources
```

Fields:

```text
id
candidate_id
source_type
url
title
source_query
summary
published_at
discovered_at
```

This supports source traceability.

---

# 27. Dashboard — Discovered Leads Queue

Add:

```text
Leads
├── All Leads
├── Add Lead
├── Import Leads
└── Discovered Leads
```

Page:

```text
/discovered-leads
```

Show:

| Company | ICP | Confidence | Location | Sources | Status | Action |
|---|---|---:|---|---:|---|---|

---

# 28. Candidate Detail Page

Example:

```text
ABC Haulage Sdn Bhd

Suggested ICP:
Logistics / Haulage

Confidence:
91%

Location:
Port Klang, Selangor

Fleet Clues:
- 80+ trucks
- Container haulage
- Port operations

Buying Signals:
- Fleet expansion
- Hiring drivers

Sources:
- Company website
- Industry directory
- News article

[ Reject ]
[ Edit ]
[ Accept as Lead ]
```

---

# 29. Candidate Review

Parimala should be able to:

```text
Accept
Edit
Reject
```

Accept flow:

```text
Candidate
   ↓
Resolve/Create Company
   ↓
Resolve/Create Contact if usable
   ↓
Create Lead
   ↓
Lead = DISCOVERED
   ↓
Candidate = ACCEPTED
```

---

# 30. Human Review Boundary

MVP1 rule:

> AI discovers and proposes. Human confirms before official Lead creation.

Do not let the discovery agent automatically:

```text
approve itself
create outreach
send email
submit Marketing Action
```

---

# 31. n8n Workflow Breakdown

Recommended workflows:

```text
Discovery Scheduler
Search Discovery
Website Fetch / Scrape
AI Company Extraction
ICP Evaluation
Candidate Deduplication
Candidate Creation
```

Exact naming may follow the current n8n convention.

---

# 32. Discovery Scheduler

The scheduler decides:

```text
which ICP
which region
which search theme
how many queries
how often
```

Example:

```text
Monday:
LOGISTICS_HAULAGE
Selangor

Tuesday:
PASSENGER_TRANSPORT
Malaysia

Wednesday:
COMMERCIAL_ENTERPRISE
Johor
```

Start small.

---

# 33. Search Limits for MVP1

Recommended initial limits:

```text
5–10 search queries per run
10–20 results per query
50–100 pages max per scheduled run
```

Keep discovery controlled.

This reduces:

```text
API cost
duplicate noise
AI cost
scraper load
review burden
```

---

# 34. Rate Limiting

n8n should throttle fetching.

Recommended starting point:

```text
1–3 requests/second maximum per domain
```

Prefer slower where appropriate.

Respect:

```text
HTTP 429
Retry-After
site restrictions
```

Do not aggressively hammer websites.

---

# 35. Caching

Avoid fetching the same URL repeatedly.

Store/check:

```text
url
last_fetched_at
content_hash if practical
```

If recently fetched and unchanged:

```text
skip
```

---

# 36. Error Handling

Each discovery item should fail independently.

Possible statuses:

```text
SEARCH_FAILED
FETCH_FAILED
PARSE_FAILED
AI_EXTRACTION_FAILED
ICP_EVALUATION_FAILED
DUPLICATE
READY
```

One failed website should not terminate an entire discovery run.

---

# 37. Retry Rules

Suggested:

```text
HTTP timeout
→ retry up to 2 times

429
→ respect Retry-After

403 / CAPTCHA
→ no aggressive retry
→ mark fallback required / blocked

AI timeout
→ retry once or twice

invalid structured AI output
→ retry with repair prompt once
```

---

# 38. Logging

Log:

```text
workflow run ID
search query
URL
fetch result
source type
candidate result
duplicate result
AI model
token/cost metadata if available
```

Never log:

```text
API keys
service tokens
credentials
```

---

# 39. Cost Control

Because MVP1 has a monthly operating cap:

```text
normal HTTP fetch first
paid scraper only as fallback
small search batches
limited AI calls
deduplicate before expensive AI where possible
cache fetched pages
```

Recommended order:

```text
cheap filter
   ↓
deduplicate
   ↓
fetch
   ↓
extract
   ↓
AI
```

Avoid AI calls on every raw result before basic filtering.

---

# 40. AI Prompt Responsibilities

The extraction model should:

```text
extract only supported facts
return null when unknown
identify evidence
suggest ICP
explain why
identify fleet clues
identify buying signals
```

The model should NOT:

```text
invent employee names
invent fleet size
invent emails
invent phone numbers
invent company location
```

---

# 41. Suggested AI Output Schema

```json
{
  "company_name": null,
  "website": null,
  "domain": null,
  "industry": null,
  "country": null,
  "state": null,
  "city": null,
  "contact_name": null,
  "job_title": null,
  "email": null,
  "phone": null,
  "linkedin_url": null,
  "fleet_clues": [],
  "buying_signals": [],
  "suggested_icp": null,
  "icp_confidence": 0.0,
  "icp_reasoning": "",
  "source_summary": ""
}
```

---

# 42. Source Evidence Requirement

For important extracted facts, preserve source evidence where practical.

Example:

```text
Fleet Clue:
"operates more than 80 prime movers"

Source:
https://example.com/about
```

The dashboard does not need to display every raw excerpt, but enough reference should be kept for verification.

---

# 43. Product Matching Boundary

Do NOT perform Product Matching during discovery.

Discovery answers:

```text
Is this company relevant enough to become a Lead?
```

Product Matching remains later:

```text
Lead
 ↓
Research
 ↓
Scoring
 ↓
Product Matching
```

---

# 44. Research Boundary

Discovery information may seed later research, but does not replace the existing Research API.

Correct:

```text
Discovery
→ Candidate
→ Lead
→ Research API
```

Not:

```text
Discovery
→ mark research complete
```

---

# 45. Social Discovery Deferred

Not part of this Level 1 implementation:

```text
LinkedIn member scraping
Facebook scraping
Instagram scraping
X scraping
logged-in social crawling
social profile harvesting
```

Social discovery is a later extension after Level 1 is validated.

---

# 46. Level 1 Definition of Done

```text
Search API integrated                          ✓
Search queries generated by ICP               ✓
Search results collected                      ✓
URL filtering works                           ✓
Normal website fetch works                    ✓
Readable text extraction works                ✓
Directory pages supported                     ✓
News/RSS supported                            ✓
AI structured extraction works                ✓
ICP evaluation works                          ✓
Source traceability preserved                 ✓
Duplicate detection works                     ✓
Lead Candidate created                        ✓
Dashboard candidate queue works               ✓
Accept/Edit/Reject works                      ✓
Accepted candidate becomes DISCOVERED Lead    ✓
No direct PostgreSQL access                   ✓
Cost controls active                          ✓
Regression validation passes                  ✓
```

---

# 47. Phase After Level 1

Once Level 1 is stable:

```text
Normal Web Discovery
        ↓
Measure:
- candidate quality
- duplicate rate
- cost
- reviewer workload
- scraper failure rate
        ↓
Add Browser/Scraper Fallback
        ↓
Validate difficult websites
        ↓
Then evaluate Social Discovery
```

---

# 48. Scraper Implementation Sequence After Level 1

When normal web discovery is proven, implement scraper fallback in this order:

```text
1. Record which websites fail normal HTTP fetch
2. Categorise failure reasons
3. Select a browser/scraping provider only if needed
4. Integrate provider through n8n HTTP/API node
5. Send only failed URLs to fallback provider
6. Retrieve rendered HTML/text
7. Pass rendered content through the SAME extraction pipeline
8. Preserve same source metadata
9. Apply same ICP evaluation
10. Apply same deduplication
11. Create/update the same Lead Candidate
12. Track cost per fallback fetch
13. Add retry/failure controls
14. Validate no duplicate candidates are created
```

The fallback scraper must not become a separate lead-generation pipeline.

It is only another retrieval method.

---

# 49. Preferred Retrieval Strategy

```text
URL
 ↓
Cached recently?
 ├── YES → reuse / skip
 └── NO
       ↓
Normal HTTP fetch
       ↓
Useful readable content?
 ├── YES → continue
 └── NO
       ↓
Fallback scraper/browser service
       ↓
Useful content?
 ├── YES → continue
 └── NO → mark FETCH_FAILED
```

Then:

```text
Readable content
      ↓
AI extraction
      ↓
ICP evaluation
      ↓
Dedup
      ↓
Candidate
```

---

# 50. Immediate Build Priority

Implement now:

```text
Search API
Company website/public page fetching
Public directories
News
RSS
AI extraction
ICP fit
Candidate queue
Source traceability
Deduplication
```

Do not start with:

```text
paid scraper
social scraping
browser automation
proxy rotation
CAPTCHA handling
```

Only introduce scraper fallback after normal Level 1 discovery produces real failure data.
