---
title: LorrySystem MVP1 — Research Worker Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1
status: ready-to-build
scope: Research Automation
created: 2026-09-27
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.


# LorrySystem MVP1 — Research Worker Handoff

## 1. Purpose

This document defines how the **Research stage** should work after a discovered Candidate is accepted and becomes a Lead.

Research should start automatically.

The Research Worker must enrich the accepted Lead with:

```text
company intelligence
fleet intelligence
technology intelligence
buying signals
possible operational pain points
relevant employees / executives
public professional profiles
public business contact details
source evidence
confidence
```

Research does **not** decide the final product to sell.

That remains the job of Product Matching.

---

# 2. High-Level Flow

```text
Discovered Candidate
        ↓
Human Accept
        ↓
Company / Contact / Lead
        ↓
Lead = DISCOVERED
        ↓
Research created
status = PENDING
        ↓
n8n Research Worker
        ↓
Research = RUNNING
Lead = RESEARCHING
        ↓
Company Research
        +
People Research
        ↓
Source collection
        ↓
Clean / deduplicate
        ↓
OpenAI structured research extraction
        ↓
Research Sources persisted
        ↓
Research = COMPLETED / PARTIAL / FAILED
        ↓
Usable Research
        ↓
Scoring
```

---

# 3. Architecture

Keep the existing architecture boundary:

```text
n8n
  ↓ authenticated HTTP / JSON
Marketing API
  ↓
PostgreSQL
```

Rules:

```text
n8n       → Marketing API ✓
n8n       → PostgreSQL    ✕

Dashboard → Marketing API ✓
Dashboard → PostgreSQL    ✕

Marketing API → PostgreSQL ✓
```

The Research Worker must not write directly to PostgreSQL.

---

# 4. Automatic Research Start

When a Candidate is accepted:

```text
Candidate Accept
      ↓
Create / reuse Company
      ↓
Create / reuse Contact
      ↓
Create Lead
      ↓
Create LeadResearch
status = PENDING
```

The operator should not need to click:

```text
Start Research
```

Initial Research starts automatically.

---

# 5. Research Worker Trigger

Recommended MVP1 approach:

```text
n8n polls for PENDING Research jobs
```

Example:

```text
Every 30–60 seconds
    ↓
GET pending Research
    ↓
claim/start one
```

This is preferred over direct Dashboard → n8n webhook coupling.

Benefits:

```text
jobs are not lost if n8n is temporarily offline
simple recovery
easy retry
Research state remains authoritative in Marketing API
```

---

# 6. Research Job Lifecycle

Use the existing lifecycle:

```text
PENDING
RUNNING
COMPLETED
PARTIAL
FAILED
```

Expected transitions:

```text
PENDING
  ↓
RUNNING
  ↓
COMPLETED
```

or:

```text
RUNNING
  ↓
PARTIAL
```

or:

```text
RUNNING
  ↓
FAILED
```

Do not leave Research permanently stuck in RUNNING.

---

# 7. Research Worker Services

For MVP1, use:

```text
Marketing API
Existing Candidate evidence
Company website
Brave Search API
Normal HTTP fetching
n8n clean-text / normalization logic
OpenAI
Research API
```

Do not make Research dependent on Level 2 or Level 3 yet.

---

# 8. Research Source Strategy

Research starts from known evidence, then expands.

```text
Candidate Evidence
        +
Company Website
        +
Company-specific Brave Search
        +
Public directories
        +
News / public webpages
```

Initial MVP1 source priority:

```text
1. Existing Candidate source
2. Official company website
3. About page
4. Services page
5. Fleet / operations page
6. Contact page
7. Careers page
8. News / media
9. Relevant public directories
10. Public professional profile references
```

---

# 9. Discovery Evidence Should Seed Research

Do not throw away Candidate evidence.

Existing Candidate context may include:

```text
company name
website
domain
source URL
source query
source summary
fleet clues
buying signals
ICP suggestion
ICP confidence
```

Use this as:

```text
Research seed context
```

But:

```text
Candidate evidence ≠ completed Research
```

Research must still perform enrichment.

---

# 10. Company Website Research

If the company domain is known:

```text
Homepage
   ↓
extract internal links
   ↓
identify useful pages
   ↓
fetch relevant pages
```

Useful page patterns:

```text
/
about
about-us
services
solutions
fleet
industries
contact
contact-us
news
blog
careers
management
team
leadership
```

Do not blindly request every guessed path.

Prefer:

```text
homepage
→ discover real internal links
→ fetch relevant links
```

---

# 11. Brave Search — Company-Specific Queries

Discovery search is broad.

Research search is targeted.

For a known company:

```text
"ABC Logistics Sdn Bhd"
"ABC Logistics Sdn Bhd" fleet
"ABC Logistics Sdn Bhd" trucks
"ABC Logistics Sdn Bhd" operations
"ABC Logistics Sdn Bhd" news
"ABC Logistics Sdn Bhd" expansion
"ABC Logistics Sdn Bhd" hiring
"ABC Logistics Sdn Bhd" GPS
"ABC Logistics Sdn Bhd" TMS
"ABC Logistics Sdn Bhd" dashcam
```

Do not necessarily run all queries.

Recommended MVP1 budget:

```text
3–4 company research queries
3–5 people research queries
```

---

# 12. Company Research Output

Research should build a structured company profile.

Target fields:

```text
company_summary
industry
main_services
locations
website
public_business_phone
public_business_email

fleet_ownership
fleet_evidence
vehicle_types
fleet_size_clues
operational_coverage

current_technology
technology_vendors_if_public

business_signals
operational_pain_points
recent_activity

research_confidence
```

Unknown values should remain:

```text
null
```

Unknown arrays:

```text
[]
```

No unsupported guessing.

---

# 13. Fleet Evidence

Use evidence classifications such as:

```text
OWNED/OPERATED
PARTNER NETWORK
CAPABILITY ONLY
OWNERSHIP UNCLEAR
```

Research should avoid assuming:

```text
"provides logistics services"
```

means:

```text
"owns a fleet"
```

unless sources support it.

---

# 14. Technology Intelligence

Look for public evidence of:

```text
GPS
TMS
DMS
dashcam
AI dashcam
MDVR
telematics
fuel monitoring
fleet management systems
route planning systems
existing vendors
```

This is evidence only.

Research does not yet decide:

```text
which LorrySystem product should be sold
```

---

# 15. Business Signals

Possible signals:

```text
fleet expansion
new vehicle purchase
driver hiring
new depot
new branch
new contract
business expansion
safety incident
fleet digitisation
fuel-cost concerns
operational growth
```

Signals should include source evidence.

---

# 16. Operational Pain Points

Research may identify supported public clues such as:

```text
fleet visibility challenges
driver safety
fuel control
route management
maintenance coordination
vehicle utilization
compliance
delivery efficiency
```

Do not invent pain points.

Only return:

```text
supported
inferred with clear confidence
or null
```

---

# 17. People Research

Research must also identify people relevant to the company.

Focus on roles that may influence or approve a LorrySystem purchase.

Do not attempt to collect every employee.

---

# 18. Relevant Roles

High priority:

```text
Founder
Owner
Managing Director
CEO
COO
General Manager
Fleet Manager
Transport Manager
Operations Manager
Logistics Manager
```

Medium priority:

```text
Safety Manager
Driver Operations Manager
IT Manager
Systems Manager
Procurement Manager
Maintenance Manager
Branch Manager
```

Low priority:

```text
general admin staff
unrelated departments
junior employees with no operational or purchasing relevance
```

---

# 19. People Research Sources

Use only public / permitted sources.

Examples:

```text
company management page
company team page
company staff directory
news articles
public business directories
public professional profile results
public LinkedIn result pages
public company social pages
public X profiles
public Facebook business pages
public Instagram business/professional accounts
```

---

# 20. People Search Queries

Examples:

```text
"ABC Logistics Sdn Bhd" managing director
"ABC Logistics Sdn Bhd" fleet manager
"ABC Logistics Sdn Bhd" operations manager
"ABC Logistics Sdn Bhd" transport manager
"ABC Logistics Sdn Bhd" director
site:linkedin.com/in "ABC Logistics Sdn Bhd"
site:linkedin.com/in "ABC Logistics" "Fleet Manager"
```

Cap people research.

Recommended:

```text
max relevant people retained = 5–10
```

---

# 21. Person Record Structure

Recommended structured output:

```json
{
  "name": "John Tan",
  "job_title": "Fleet Manager",
  "department": "Operations",
  "relevance": "HIGH",
  "role_classification": "DECISION_MAKER",
  "linkedin_url": "https://linkedin.com/in/...",
  "other_professional_profiles": [],
  "business_email": null,
  "business_phone": null,
  "source_url": "https://company.com/team",
  "confidence": 0.92
}
```

---

# 22. Person Role Classification

Recommended classifications:

```text
EXECUTIVE
DECISION_MAKER
INFLUENCER
OPERATIONAL_CONTACT
LOW_RELEVANCE
```

Example:

```text
Managing Director
→ EXECUTIVE

Fleet Manager
→ DECISION_MAKER

Operations Manager
→ DECISION_MAKER

Safety Manager
→ INFLUENCER

Driver
→ LOW_RELEVANCE
```

---

# 23. Public Professional Handles

Research may retain:

```text
public LinkedIn URL
public professional X profile
public Facebook business/professional page
public Instagram business/professional profile
other public professional profile
```

Do not retain unrelated personal social accounts.

---

# 24. Important Boundaries

Allowed:

```text
public professional profiles
public company staff pages
public business emails
public business phone numbers
public role/title information
public company social pages
search-indexed professional profiles
```

Do not implement:

```text
private profile scraping
login bypass
CAPTCHA bypass
member-only harvesting
mass employee scraping
personal social account collection unrelated to work
```

---

# 25. Email Handling

Do not invent email addresses.

Forbidden example:

```text
John Tan
+
company domain
→ guess john.tan@company.com
```

unless a future enrichment service explicitly verifies it.

For MVP1:

```text
publicly shown business email → retain
not publicly supported → null
```

---

# 26. Contact Creation Policy

Do NOT automatically convert every discovered person into a normal Contact record.

Recommended flow:

```text
Relevant Person Found
        ↓
Verify company association
        ↓
Confidence high?
   ┌────────────┴────────────┐
  YES                        NO
   │                          │
Eligible for Contact      Keep only as
creation/linking          Research evidence
```

This avoids polluting Contacts with weak or incorrect identities.

---

# 27. Research Source Storage

Every useful source must be persisted through the existing Research Source system.

Conceptually:

```text
LeadResearch
├── Company Website
├── About Page
├── Services Page
├── Fleet Page
├── Contact Page
├── News Source
├── Management Page
└── Public Professional Source
```

Store where supported:

```text
source_type
url
title
retrieved_at
summary
evidence
```

---

# 28. Evidence Requirement

Important claims should remain traceable.

Example:

```text
Fleet evidence:
"Operates more than 80 prime movers"

Source:
https://example.com/fleet
```

Example:

```text
Relevant person:
Jane Lim — Operations Manager

Source:
https://example.com/management
```

---

# 29. Source Deduplication

Before AI processing:

```text
deduplicate URLs
deduplicate repeated page text
remove repeated navigation/footer noise
avoid sending the same evidence multiple times
```

---

# 30. AI Strategy

Prefer one structured AI call after collecting useful evidence.

Avoid:

```text
Page 1 → OpenAI
Page 2 → OpenAI
Page 3 → OpenAI
Page 4 → OpenAI
```

Preferred:

```text
Fetch Sources
    ↓
Clean Text
    ↓
Deduplicate
    ↓
Build Research Context
    ↓
ONE OpenAI structured extraction call
```

---

# 31. Suggested AI Output

```json
{
  "company_summary": null,
  "industry": null,
  "main_services": [],
  "locations": [],
  "fleet": {
    "ownership": null,
    "vehicle_types": [],
    "size_clues": [],
    "evidence": []
  },
  "current_technology": [],
  "business_signals": [],
  "operational_pain_points": [],
  "relevant_people": [],
  "research_confidence": 0.0
}
```

---

# 32. AI Rules

The model must:

```text
extract only supported facts
return null when unknown
keep unsupported arrays empty
preserve evidence/source relationships where practical
classify relevant people
classify fleet ownership carefully
identify business signals
identify operational clues
```

The model must not:

```text
invent employees
invent emails
invent phone numbers
invent fleet size
invent technology vendors
invent company locations
invent social handles
```

---

# 33. Research Budget Per Lead

Recommended MVP1 limits:

```text
Company pages       max 5
Brave company queries max 4
People queries      max 5
External sources    max 5
Total fetched URLs  max 10–15
Relevant people     max 5–10
OpenAI calls        1
```

Tune after testing.

---

# 34. Example Research Run

```text
ABC Haulage

Candidate source          1
Homepage                  1
About                     1
Services                  1
Fleet                     1
Contact                   1
Management                1
News                      2
LinkedIn/public profiles  2
---------------------------
Total evidence           11

OpenAI calls              1
```

---

# 35. Level 2 Dependency

Research MVP1 should NOT depend on Level 2.

Current behavior:

```text
normal HTTP fetch
      ↓
blocked source?
      ↓
mark unavailable
      ↓
continue with remaining evidence
```

Later, after Level 2 is completed:

```text
normal fetch fails
      ↓
ZenRows fallback
```

can be reused by Research.

---

# 36. Level 3 / Social Dependency

Do NOT make Research depend on unfinished Level 3 Social Discovery.

Initial Research may use:

```text
public search-indexed professional/social results
public company pages
public professional URLs
```

But do not build unrestricted social scraping into Research.

---

# 37. Research Result Status

Recommended:

```text
COMPLETED
```

when enough reliable evidence exists.

Use:

```text
PARTIAL
```

when useful research exists but important sections are missing.

Use:

```text
FAILED
```

when research cannot produce meaningful usable output.

---

# 38. Example COMPLETED

```text
company identity confirmed
website confirmed
services confirmed
fleet evidence available
at least one relevant source
structured Research generated
```

Contact discovery does not have to succeed for Research to be COMPLETED.

---

# 39. Example PARTIAL

```text
company identified
basic services known
very little fleet evidence
no official site
limited source coverage
```

Still usable for Scoring if current Scoring rules allow PARTIAL Research.

---

# 40. Retry Logic

Recommended:

```text
HTTP timeout
→ retry up to 2 times

429
→ respect Retry-After

403
→ do not aggressively retry

OpenAI timeout
→ retry once

invalid structured AI output
→ one repair/retry attempt
```

---

# 41. Stale RUNNING Recovery

Later add protection such as:

```text
RUNNING longer than 30 minutes
→ recover / mark retryable
```

Do not leave Research permanently stuck because of an n8n crash.

---

# 42. Lead Status Interaction

When Research starts:

```text
Lead:
DISCOVERED
→ RESEARCHING
```

Research completion alone should NOT automatically mean:

```text
QUALIFIED
```

Qualification remains the responsibility of Scoring.

---

# 43. Trigger Scoring

When Research is:

```text
COMPLETED
```

or a usable:

```text
PARTIAL
```

then:

```text
n8n
→ Scoring API
```

Future pipeline:

```text
Candidate Accept
      ↓
Research
      ↓
Scoring
      ↓
Product Matching
      ↓
Marketing Action
```

---

# 44. Dashboard Research Section

Lead Detail should eventually display:

```text
Research

Status:
COMPLETED

Last Researched:
<date>

Sources:
8

Company Summary:
...

Fleet:
...

Technology:
...

Buying Signals:
...

Relevant People:
- Jane Lim — Managing Director
- Kumar Raj — Fleet Manager
- Ahmad — Operations Manager

[ View Research ]
[ Re-run Research ]
```

---

# 45. Initial Research State

For a newly accepted Lead:

```text
Research
Status: PENDING
```

then:

```text
RUNNING
```

then:

```text
COMPLETED / PARTIAL / FAILED
```

No manual first-start button required.

---

# 46. Re-run Research

Initial Research is automatic.

Later allow:

```text
[ Re-run Research ]
```

Each re-run should preserve historical Research runs.

Do not overwrite old Research history.

---

# 47. n8n Workflow Breakdown

Recommended workflow sections:

```text
A — Research Worker Trigger
B — Find PENDING Research
C — Claim / Start Research
D — Load Lead / Company / Candidate Context
E — Company Website Research
F — Brave Company Search
G — People Search
H — Fetch Public Sources
I — Clean / Deduplicate
J — Build Research Context
K — OpenAI Structured Research
L — Validate Research Output
M — Add Research Sources
N — Complete / Partial / Fail Research
O — Trigger Scoring
P — Run Summary
```

---

# 48. Research Worker Run Summary

At the end, return:

```text
research_id
lead_id
company_name
sources_found
sources_fetched
sources_failed
company_pages_used
external_sources_used
people_found
high_relevance_people
research_status
research_confidence
scoring_triggered
```

---

# 49. Validation Scenarios

Test:

```text
1. Lead with official website
2. Lead with no website
3. Lead with strong fleet evidence
4. Lead with weak fleet evidence
5. Lead with public management page
6. Lead with public LinkedIn professional results
7. Lead with no relevant people found
8. Lead with conflicting person/company association
9. Lead with blocked source
10. Lead with partial evidence
11. OpenAI timeout
12. invalid AI structured output
13. duplicate Research start
14. stale RUNNING Research recovery
15. successful COMPLETED → Scoring trigger
```

---

# 50. Definition of Done

```text
Automatic Research creation after Candidate Accept     ✓
PENDING Research can be discovered by n8n              ✓
Research can be atomically started                      ✓
Lead becomes RESEARCHING                                ✓

Existing Candidate evidence reused                      ✓
Company website research works                          ✓
Company-specific Brave queries work                     ✓
Public external source retrieval works                  ✓

People research works                                   ✓
Relevant roles prioritised                              ✓
Public LinkedIn URLs retained when supported            ✓
Other professional handles retained when supported      ✓
No invented employee/contact data                       ✓
No private/login-only scraping                          ✓

Research Sources persisted                              ✓
Source traceability preserved                           ✓
Structured company Research generated                   ✓
Relevant people structured                              ✓
Research confidence generated                           ✓

COMPLETED path works                                     ✓
PARTIAL path works                                       ✓
FAILED path works                                        ✓
Retry behavior works                                     ✓

Usable Research triggers Scoring                        ✓
No direct PostgreSQL access from n8n                    ✓
Regression passes                                        ✓
```

---

# 51. Recommended Build Order

```text
1. Inspect current LeadResearch model/schema
2. Inspect ResearchSource model/schema
3. Inspect Research router/service
4. Inspect current n8n Research workflow
5. Confirm automatic PENDING Research creation path
6. Confirm PENDING Research listing/query method
7. Confirm atomic PENDING → RUNNING start behavior
8. Define Research output schema
9. Define relevant_people schema
10. Implement Candidate-context loading
11. Implement company website research
12. Implement company-specific Brave queries
13. Implement people search queries
14. Implement source fetching
15. Implement clean/dedup stage
16. Implement combined OpenAI Research extraction
17. Persist Research Sources
18. Complete / Partial / Failed handling
19. Add Dashboard Research display
20. Trigger Scoring
21. Run Research regression
22. Freeze Research
```

---

# 52. Immediate Next Task

Start by inspecting:

```text
LeadResearch SQLAlchemy model
ResearchSource SQLAlchemy model
Research Pydantic schemas
Research router
Research service
Candidate Accept service
existing n8n Research workflow
```

Then determine:

```text
1. What Research fields already exist?
2. What ResearchSource fields already exist?
3. Can relevant people fit the current schema?
4. Do we need a new table for researched people?
5. Can Candidate Accept already create PENDING Research?
6. Can n8n query PENDING Research safely?
```

Do not create a migration until the current Research schema is inspected.

---

# 53. Responsibility Boundary

Keep this separation strict:

```text
Research
= What do we know about this company and its relevant people?

Scoring
= How qualified / valuable is this Lead?

Product Matching
= Which LorrySystem product fits best?

Marketing Action
= What should we say to them?
```

This separation should remain unchanged throughout MVP1.
