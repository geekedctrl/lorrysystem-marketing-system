---
title: LorrySystem MVP1 Level 2 Lead Discovery — Browser/Scraper Fallback Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
date: 2026-09-19
status: planned-after-level-1
scope: Difficult Website Retrieval / Browser Scraper Fallback
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem MVP1 Level 2 Lead Discovery — Browser/Scraper Fallback Handoff

## 1. Purpose

This document defines **Level 2** of the MVP1 AI Lead Discovery system.

Level 2 is only implemented **after Level 1 normal web discovery is working and has produced real failure data**.

Level 2 exists to retrieve public business pages that cannot be reliably fetched using ordinary HTTP requests.

Level 2 does NOT replace Level 1.

The retrieval priority remains:

```text
Normal HTTP Fetch
        ↓
Works?
 ┌──────┴──────┐
 YES            NO
 │               │
Continue      Level 2 Fallback
 │               │
 └───────┬───────┘
         ▼
  Same Extraction Pipeline
```

---

# 2. Level 2 Objective

Level 2 should solve cases such as:

```text
JavaScript-rendered company websites
dynamic public directories
sites returning empty HTML shells
anti-bot interstitials that allow normal browser access
pages whose useful content appears only after rendering
```

It must NOT be designed to:

```text
bypass login walls
bypass CAPTCHAs
evade access controls
scrape private/member-only content
circumvent platform restrictions
```

---

# 3. Architecture

Recommended architecture:

```text
n8n
 │
 ├── receives failed Level 1 URLs
 │
 ├── classifies retrieval failure
 │
 ├── calls browser/scraper provider
 │
 ├── receives rendered public content
 │
 └── sends content into existing AI extraction pipeline
 │
 ▼
AI Extraction
 │
 ▼
ICP Evaluation
 │
 ▼
Deduplication
 │
 ▼
Lead Candidate
 │
 ▼
Dashboard Review
```

Hard rules:

```text
Scraper Provider ✕ PostgreSQL
Scraper Provider ✕ Marketing API credentials
Scraper Provider ✕ Dashboard credentials

n8n ✓ Scraper Provider API
n8n ✓ Marketing API
Marketing API ✓ PostgreSQL
```

---

# 4. Trigger Conditions

A URL should enter Level 2 only when Level 1 marks it as one of:

```text
RENDER_REQUIRED
FETCH_FAILED_JS
FETCH_FAILED_EMPTY_CONTENT
FETCH_FAILED_INTERSTITIAL
```

Do not send every URL through the paid/browser fallback.

---

# 5. Failure Classification

Before invoking Level 2, classify why normal retrieval failed.

Suggested values:

```text
HTTP_403
HTTP_429
JS_RENDER_REQUIRED
EMPTY_HTML
ANTI_BOT_PAGE
TIMEOUT
CONTENT_TOO_LOW
UNSUPPORTED_RESPONSE
UNKNOWN
```

This classification should be logged for later tuning.

---

# 6. Fallback Decision Rules

Recommended behavior:

```text
JS_RENDER_REQUIRED
→ Level 2 eligible

EMPTY_HTML
→ Level 2 eligible

CONTENT_TOO_LOW
→ Level 2 eligible

ANTI_BOT_PAGE
→ Level 2 may be attempted only if provider retrieves the same public page normally

HTTP_403
→ one controlled fallback attempt maximum

HTTP_429
→ respect Retry-After first
→ do not immediately escalate

LOGIN_REQUIRED
→ stop

CAPTCHA_REQUIRED
→ stop

PRIVATE_CONTENT
→ stop
```

---

# 7. Scraper / Browser Provider Role

The provider should do only:

```text
render public webpage
return readable HTML/text
optionally execute page JavaScript
optionally wait for main content
```

The provider should not:

```text
decide ICP
create leads
deduplicate companies
store business records
make approval decisions
```

n8n remains the orchestrator.

---

# 8. Provider Selection Criteria

Choose a provider based on:

```text
cost
reliability
JavaScript rendering
API simplicity
response speed
usage limits
supported locations
data retention policy
security
```

Prefer providers that support:

```text
single-page fetch
rendered HTML
plain-text extraction
usage metering
request timeout
```

Do not select a provider solely because it offers aggressive anti-bot bypass features.

---

# 9. Cost-Control Rule

Level 2 should be:

```text
fallback only
```

not:

```text
default retrieval path
```

Recommended:

```text
Level 1 normal fetch
        ↓
failure
        ↓
dedup / check cache
        ↓
Level 2 fallback
```

Avoid paying twice for recently fetched or duplicate URLs.

---

# 10. Browser Fetch Output

Capture:

```text
requested_url
final_url
http_status if provided
render_status
rendered_html or readable_text
retrieval_provider
retrieved_at
provider_cost metadata if available
```

---

# 11. Content Cleanup

After rendered content is returned:

```text
remove scripts
remove styles
remove repeated navigation
remove cookie-banner noise
remove irrelevant footer text
extract readable business content
```

Feed the cleaned content into the SAME downstream extraction pipeline used by Level 1.

---

# 12. Same AI Extraction Pipeline

Do not create separate extraction prompts for Level 2 unless technically required.

Reuse:

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

Unknown values must remain:

```text
null
```

---

# 13. Source Traceability

Preserve both:

```text
original source URL
retrieval method
```

Example:

```text
source_type = COMPANY_WEBSITE
source_url = https://example.com
retrieval_method = BROWSER_FALLBACK
provider = <provider-name>
```

This allows later analysis of which sites required Level 2.

---

# 14. Caching

Before calling a paid fallback:

```text
check whether URL was already successfully rendered recently
```

If yes:

```text
reuse cached content where appropriate
```

Recommended cache metadata:

```text
url
retrieval_method
last_fetched_at
content_hash
last_success
```

---

# 15. Retry Policy

Suggested:

```text
timeout
→ retry once

provider temporary 5xx
→ retry once

429
→ respect provider retry instructions

403 after fallback
→ stop

CAPTCHA
→ stop

login required
→ stop
```

Do not create infinite retry loops.

---

# 16. n8n Workflow Structure

Recommended Level 2 workflow:

```text
Fallback Queue
    ↓
Failure Classification
    ↓
Cache Check
    ↓
Browser/Scraper API
    ↓
Response Validation
    ↓
Readable Text Extraction
    ↓
AI Extraction
    ↓
ICP Evaluation
    ↓
Deduplication
    ↓
Candidate Create/Update
```

---

# 17. Candidate Behavior

Level 2 should update the SAME Lead Candidate system used by Level 1.

Possible behaviors:

```text
new company
→ create candidate

existing candidate
→ enrich candidate with new source

existing active lead
→ do not create duplicate candidate

possible duplicate
→ flag for review
```

---

# 18. Failure Outcomes

Possible statuses:

```text
FALLBACK_SUCCESS
FALLBACK_FAILED
BLOCKED
LOGIN_REQUIRED
CAPTCHA_REQUIRED
TIMEOUT
NO_USEFUL_CONTENT
DUPLICATE
```

Failures should remain visible for diagnostics.

---

# 19. Dashboard Visibility

Candidate detail may show:

```text
Source:
Company Website

Retrieval:
Browser Fallback

Status:
Successful
```

Admin/system diagnostics may also show:

```text
normal fetch failed
fallback succeeded
```

Parimala does not need low-level scraper details unless useful.

---

# 20. Security Requirements

Provider API keys must remain:

```text
server-side
inside n8n credential storage or secret store
never in browser
never in workflow exports if avoidable
never in logs
```

Provider must not receive:

```text
Marketing API key
PostgreSQL password
Dashboard session secret
n8n encryption key
```

---

# 21. Data Minimisation

Send only what the fallback provider needs:

```text
target URL
render options
```

Do not send:

```text
internal lead database
contact history
approval data
API credentials
```

---

# 22. Observability

Track:

```text
number of Level 1 failures
number sent to Level 2
fallback success rate
fallback failure rate
average cost per rendered page
average latency
duplicate rate
candidate yield
```

---

# 23. Cost Guardrails

Recommended controls:

```text
daily Level 2 request cap
monthly budget cap
per-domain retry cap
cache reuse
skip duplicate URLs
```

If monthly cost exceeds plan:

```text
pause Level 2 automatically
or
require manual re-enable
```

---

# 24. Definition of Done

Level 2 is complete when:

```text
Level 1 failures are classified                  ✓
fallback queue works                             ✓
browser/scraper provider integrated              ✓
provider credentials secured                     ✓
only failed URLs use fallback                    ✓
rendered content is validated                    ✓
same AI extraction pipeline reused               ✓
same ICP evaluation reused                       ✓
same deduplication reused                        ✓
candidate enrichment works                       ✓
source traceability preserved                    ✓
blocked/private pages stop safely                ✓
cost tracking works                              ✓
rate/retry limits work                           ✓
regression validation passes                     ✓
```

---

# 25. Exit Gate to Level 3

Before starting social discovery, measure:

```text
Level 1 candidate quality
Level 2 recovery rate
cost per accepted candidate
duplicate rate
review workload
failed-domain patterns
```

Proceed to Level 3 only when Web Discovery is stable.
