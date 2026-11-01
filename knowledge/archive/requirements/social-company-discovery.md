---
title: LorrySystem MVP1 Level 3 Lead Discovery — Controlled Social Discovery Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
date: 2026-09-19
status: planned-after-level-2
scope: Controlled Public Social Discovery
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem MVP1 Level 3 Lead Discovery — Controlled Social Discovery Handoff

## 1. Purpose

This document defines **Level 3** of the MVP1 AI Lead Discovery system.

Level 3 adds controlled discovery from social sources after:

```text
Level 1 Web Discovery
        ↓
Level 2 Browser/Scraper Fallback
        ↓
Level 3 Social Discovery
```

Level 3 must remain consistent with the MVP1 roadmap:

```text
controlled discovery
human review
source traceability
no unrestricted LinkedIn/member scraping
```

---

# 2. Level 3 Objective

Use public and permitted social sources to identify:

```text
relevant companies
fleet-related activity
business growth signals
transport/logistics activity
possible decision-maker references
buying signals
```

Then send those findings into the SAME candidate pipeline used by Web Discovery.

---

# 3. Architecture

Recommended:

```text
                     n8n
                      │
        ┌─────────────┼─────────────┐
        │             │             │
        ▼             ▼             ▼
 Official APIs   Data Providers   Public Indexed
 where allowed   where justified  Social Pages
        │             │             │
        └─────────────┴─────────────┘
                      ↓
                 Raw Social Data
                      ↓
                AI Signal Extraction
                      ↓
                 Company Resolution
                      ↓
                  ICP Evaluation
                      ↓
                   Deduplication
                      ↓
                  Lead Candidate
                      ↓
                 Dashboard Review
```

---

# 4. n8n Role

n8n remains the orchestrator.

It should:

```text
schedule queries
call approved social APIs/providers
normalize returned data
send text to AI
resolve company identity
deduplicate
create/enrich candidates through Marketing API
```

n8n should NOT:

```text
store data directly in PostgreSQL
hold social credentials in plain workflow JSON
bypass login/access controls
automatically approve leads
```

---

# 5. Permitted Source Strategy

Preferred order:

```text
1. Official platform API
2. Approved third-party data provider
3. Public search-engine indexed social/company pages
```

Do not begin by building custom logged-in social scrapers.

---

# 6. Platform Scope

Potential sources:

```text
LinkedIn company activity where API/provider access permits
Facebook public business pages
Instagram public business accounts
X public posts/accounts
public social references surfaced by search engines
```

Exact platform support depends on lawful/technical API access.

---

# 7. Explicitly Out of Scope

Do NOT implement:

```text
unrestricted LinkedIn member scraping
credential-based account scraping
private profile harvesting
login bypass
CAPTCHA bypass
anti-bot evasion
mass personal-profile crawling
automated connection requests
automated unsolicited messaging
```

---

# 8. Social Discovery Targets

The goal is primarily to discover or enrich companies.

Useful findings include:

```text
company name
company page/profile URL
industry
location
website/domain
public contact info
fleet references
transport activity
expansion signals
new depot/branch
vehicle purchase
driver hiring
new contracts
safety-related posts
fuel/fleet pain points
```

---

# 9. Buying-Signal Categories

Recommended signal types:

```text
FLEET_EXPANSION
NEW_VEHICLE_PURCHASE
DRIVER_HIRING
NEW_DEPOT
NEW_BRANCH
NEW_CONTRACT
SAFETY_INCIDENT
DRIVER_SAFETY_FOCUS
FUEL_COST_CONCERN
TRACKING_VISIBILITY_NEED
FLEET_DIGITISATION
BUSINESS_EXPANSION
```

These are hints, not proof of purchase intent.

---

# 10. Social Data Extraction

For each public item capture:

```text
platform
company/account name
profile/page URL
post URL
published_at
text/summary
source title
discovered_at
```

AI may derive:

```text
company_name
domain if present
location
signal_type
signal_confidence
signal_summary
suggested_icp
icp_confidence
```

---

# 11. Company Resolution

Social data must be mapped to a business identity.

Resolution order:

```text
1. domain from social/company page
2. website link
3. exact company name
4. normalized company name
5. location + company-name combination
```

If ambiguous:

```text
NEEDS_REVIEW
```

Do not guess.

---

# 12. Candidate Integration

Social discovery should NOT create a separate lead system.

It should use the same:

```text
Lead Candidate
Candidate Sources
Deduplication
Review
Promotion to Lead
```

pipeline from Level 1/2.

---

# 13. Candidate Enrichment

If a candidate already exists from Web Discovery:

```text
add social source
add buying signal
update evidence
```

Do not create another candidate for the same company.

Example:

```text
Candidate:
ABC Logistics

Existing Sources:
- Company website

New Social Evidence:
- Facebook public post announcing 20 new trucks
```

---

# 14. Social Candidate Review

Dashboard candidate detail may show:

```text
ABC Logistics Sdn Bhd

Suggested ICP:
LOGISTICS_HAULAGE

Confidence:
92%

Web Evidence:
- company website

Social Signals:
- announced fleet expansion
- hiring heavy-vehicle drivers

Sources:
- company website
- public Facebook post

[ Reject ]
[ Edit ]
[ Accept as Lead ]
```

---

# 15. Human Review Boundary

MVP1 rule remains:

> AI discovers and proposes. Human confirms before official Lead creation.

Social signals must never directly cause:

```text
automatic email
automatic DM
automatic social comment
automatic lead approval
```

---

# 16. Source Traceability

Every social source must preserve:

```text
platform
source_url
source_type
published_at if available
discovered_at
source_query / discovery method
summary
```

Do not save unsupported claims without a source.

---

# 17. Social Query Strategy

Queries should be ICP-driven.

Examples:

```text
logistics company Malaysia fleet expansion
haulage company Malaysia new trucks
bus operator Malaysia new fleet
transport company Selangor hiring drivers
commercial fleet Malaysia new depot
```

Search may be done through:

```text
official platform APIs
provider search endpoints
web search restricted to social domains
```

---

# 18. Search-Engine Indexed Social Pages

A low-cost method is:

```text
site:linkedin.com/company haulage Malaysia
site:facebook.com logistics fleet Selangor
site:x.com transport Malaysia fleet
```

Use only publicly indexed results.

Do not treat a search snippet as sufficient evidence when the underlying page is inaccessible.

---

# 19. Official APIs

Where official APIs are available, use them preferentially.

Benefits:

```text
clear access model
structured data
lower scraping maintenance
stable identifiers
better compliance posture
```

Limitations may include:

```text
permissions
app review
rate limits
restricted fields
cost
```

---

# 20. Third-Party Social Data Providers

Use a third-party provider only when:

```text
official API is unavailable or insufficient
provider terms allow the required use
cost fits MVP1 budget
data quality is acceptable
```

Provider should return structured public/business data where possible.

---

# 21. Provider Security

Social provider credentials must remain:

```text
inside n8n credential storage / server-side secrets
never in browser
never in logs
never embedded into public workflow exports
```

Do not share:

```text
Marketing API key
PostgreSQL password
Dashboard session secret
```

with social providers.

---

# 22. Rate Limiting

Respect provider/platform rate limits.

n8n should:

```text
batch requests
wait between calls
respect Retry-After
stop on persistent 429
```

Do not aggressively retry blocked requests.

---

# 23. Data Minimisation

Store only information relevant to lead generation.

Prefer:

```text
company/business information
public business contact information
public company posts
business signals
```

Avoid collecting unrelated personal data.

---

# 24. Contact Discovery

Possible business contact fields:

```text
contact_name
job_title
business_email
business_phone
linkedin_url
```

Do not invent or infer personal details.

If a social source only identifies:

```text
Operations Manager
```

without a verified name:

```text
contact_name = null
job_title = Operations Manager
```

---

# 25. AI Signal Extraction

The AI should return structured output.

Suggested:

```json
{
  "company_name": null,
  "website": null,
  "domain": null,
  "platform": null,
  "profile_url": null,
  "post_url": null,
  "signal_type": null,
  "signal_confidence": 0.0,
  "signal_summary": "",
  "suggested_icp": null,
  "icp_confidence": 0.0,
  "icp_reasoning": "",
  "contact_name": null,
  "job_title": null,
  "email": null,
  "phone": null,
  "linkedin_url": null
}
```

Unknown values remain:

```text
null
```

---

# 26. Signal Confidence

Suggested:

```text
0.90+  strong evidence
0.75+  useful signal
0.50+  uncertain
<0.50  weak/noisy
```

Signal confidence and ICP confidence are separate.

---

# 27. Deduplication

Before candidate creation/enrichment, compare:

```text
domain
website
normalized company name
existing company
existing lead
existing candidate
existing social source URL
```

Do not repeatedly add the same post/source.

---

# 28. Candidate Outcomes

Possible outcomes:

```text
NEW_CANDIDATE
ENRICH_EXISTING_CANDIDATE
EXISTING_COMPANY
EXISTING_ACTIVE_LEAD
POSSIBLE_DUPLICATE
WEAK_SIGNAL
REJECTED
```

---

# 29. Social Source Storage

Prefer reusing the candidate source model.

Source types may include:

```text
SOCIAL_LINKEDIN
SOCIAL_FACEBOOK
SOCIAL_INSTAGRAM
SOCIAL_X
SOCIAL_OTHER
```

Do not create separate platform-specific candidate tables unless later required.

---

# 30. Dashboard Changes

Candidate list may gain:

```text
Source filter:
Web
Directory
News
Social
```

Candidate detail may show a section:

```text
Social Signals
```

Example:

| Platform | Signal | Confidence | Date |
|---|---|---:|---|
| Facebook | Fleet expansion | 88% | 2026-09-18 |
| LinkedIn | Hiring drivers | 81% | 2026-09-15 |

---

# 31. n8n Workflow Breakdown

Recommended:

```text
Social Discovery Scheduler
Social Search/API Query
Social Data Normalizer
AI Signal Extraction
Company Resolution
ICP Evaluation
Candidate Deduplication
Candidate Enrichment/Create
```

---

# 32. Scheduling

Start small.

Example:

```text
Monday:
LOGISTICS_HAULAGE social scan

Wednesday:
PASSENGER_TRANSPORT social scan

Friday:
COMMERCIAL_ENTERPRISE social scan
```

Avoid continuous high-frequency scraping in MVP1.

---

# 33. Volume Limits

Suggested starting limits:

```text
20–50 social items per run
5–10 candidate companies per run
small number of API/provider calls
```

Tune after measuring review quality.

---

# 34. Error Handling

Possible statuses:

```text
SOCIAL_QUERY_FAILED
SOURCE_UNAVAILABLE
RATE_LIMITED
SOURCE_PRIVATE
PARSE_FAILED
AI_EXTRACTION_FAILED
COMPANY_UNRESOLVED
DUPLICATE
READY
```

One failed source must not fail the entire workflow.

---

# 35. Retry Rules

Suggested:

```text
provider timeout
→ retry once

temporary 5xx
→ retry once

429
→ respect Retry-After

permission denied
→ stop

private/login-only content
→ stop

invalid AI output
→ one repair attempt
```

---

# 36. Logging

Track:

```text
workflow run ID
platform
query
source URL
provider
result
company resolution result
signal type
candidate result
cost metadata if available
```

Never log credentials.

---

# 37. Cost Control

Level 3 must fit the MVP1 operating cap.

Use:

```text
small search batches
provider quotas
dedup before AI where possible
reuse existing candidates
skip already-seen source URLs
limit expensive enrichment calls
```

---

# 38. Quality Metrics

Measure:

```text
social items scanned
companies resolved
candidates created
existing candidates enriched
accepted candidates
false-positive rate
duplicate rate
cost per accepted candidate
Parimala review time
```

---

# 39. Separation From Outreach

Social Discovery is only for:

```text
discovery
evidence
candidate enrichment
buying signals
```

It does NOT mean:

```text
auto-comment
auto-DM
auto-follow
auto-post
```

Those are separate marketing execution capabilities.

---

# 40. Definition of Done

Level 3 is complete when:

```text
approved social source method selected           ✓
provider/API credentials secured                 ✓
public/permitted social data retrieved           ✓
social items normalized                          ✓
company resolution works                         ✓
buying-signal extraction works                   ✓
ICP evaluation works                             ✓
source traceability preserved                    ✓
duplicate social sources prevented               ✓
existing candidates can be enriched              ✓
new candidates can be created                    ✓
dashboard shows social evidence                  ✓
human review remains mandatory                   ✓
no direct PostgreSQL access                      ✓
cost controls active                             ✓
regression validation passes                     ✓
```

---

# 41. Final MVP1 Discovery Architecture

After Level 3:

```text
                    AI DISCOVERY
                         │
          ┌──────────────┼──────────────┐
          │              │              │
          ▼              ▼              ▼
     Level 1 Web     Level 2        Level 3
       Discovery     Fallback        Social
          │              │              │
          └──────────────┴──────────────┘
                         ↓
                    AI Extraction
                         ↓
                     ICP Match
                         ↓
                    Deduplication
                         ↓
                    Lead Candidate
                         ↓
                   Human Review
                         ↓
              Company + Contact + Lead
                         ↓
                    DISCOVERED
```

---

# 42. Exit Gate

Level 3 should be considered successful when:

```text
social discovery improves candidate quality
review workload remains manageable
false-positive rate is acceptable
cost remains inside MVP1 cap
source traceability is intact
no unrestricted/private scraping is used
```

Once this is stable, the Lead Generation discovery side of MVP1 can be considered functionally complete.
