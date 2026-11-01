---
title: LorrySystem Lead Generation — Business Card & CSV Import Handoff
project: LorrySystem AI Marketing & Lead Generation
stage: MVP1 Dashboard Enhancement
date: 2026-09-19
status: ready-to-build
next_migration_id_if_needed: "007"
---

> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Lead Generation — Business Card & CSV Import Handoff

## 1. Purpose

This document defines the MVP1 requirements for expanding lead generation through:

```text
1. Business Card Image Upload
2. CSV Lead Import
```

AI web scraping / autonomous lead discovery is explicitly OUT OF SCOPE for this build.

The design principle is:

> Business Card upload acts as a **smart autofill system**, while CSV upload acts as a **bulk lead import system**.

Both methods must use the existing Marketing API and existing Companies / Contacts / Leads business rules.

Do not bypass the API with direct PostgreSQL writes.

---

# 2. Architecture — MUST PRESERVE

```text
Browser
   ↓
Dashboard
   ↓
Marketing API
   ↓
PostgreSQL
```

Hard rules:

```text
Dashboard ✕ PostgreSQL
n8n       ✕ PostgreSQL

Dashboard ✓ Marketing API
n8n       ✓ Marketing API
Marketing API ✓ PostgreSQL
```

All imported data must flow through the Marketing API so existing validation, duplicate protection, lifecycle rules, and event logging remain active.

---

# 3. Scope

Included:

```text
Business Card image upload
OCR / Vision extraction
Smart autofill review form
Manual correction before submit
CSV template
CSV upload
CSV parsing
Row validation
Duplicate handling
Import preview
Bulk import execution
Import summary
Nullable optional company/contact fields
```

Not included:

```text
AI web scraping
autonomous lead discovery
automatic outreach
automatic approval
direct DB imports
full CRM import engine
```

---

# 4. Business Card Upload

Business Card upload should behave as:

```text
Upload Image
    ↓
OCR / Vision Extraction
    ↓
Extract Fields
    ↓
Autofill Form
    ↓
Parimala Reviews / Corrects
    ↓
Select ICP
    ↓
Select Priority
    ↓
Create Company / Contact / Lead
```

The OCR result must never be written directly to the database without user review.

Business Card upload is:

```text
SMART AUTOFILL
```

not:

```text
AUTOMATIC INSERT
```

---

# 5. Business Card Fields

Attempt to extract:

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
```

Fields not detected remain blank.

The user must provide:

```text
icp
```

Priority:

```text
LOW
MEDIUM
HIGH
```

If not explicitly selected:

```text
MEDIUM
```

---

# 6. Business Card Review Screen

Example:

```text
Company Name
[ ABC Logistics Sdn Bhd ]

Website
[ https://abc.com ]

Domain
[ abc.com ]

Industry
[ Logistics ]

Country
[ Malaysia ]

State
[ Selangor ]

City
[ Klang ]

Contact Name
[ John Tan ]

Job Title
[ Operations Manager ]

Email
[ john@abc.com ]

Phone
[ +60123456789 ]

LinkedIn URL
[ ]

ICP
[ Logistics / Haulage ▼ ]

Priority
[ MEDIUM ▼ ]

[ Cancel ]   [ Create Lead ]
```

All extracted values must remain editable.

---

# 7. Business Card Validation

Required:

```text
company_name
icp
```

Optional:

```text
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
priority
```

Do not create an empty Contact row.

A Contact should only be created when at least one meaningful field exists:

```text
contact_name
job_title
email
phone
linkedin_url
```

---

# 8. Business Card Final Create Flow

```text
1. Find or create Company
2. Create Contact only if contact data exists
3. Create Lead
4. Lead starts as DISCOVERED
5. Redirect to Lead Detail
```

Do not manually force another initial lead status.

---

# 9. CSV Import

CSV upload should support bulk lead creation.

Flow:

```text
Download Template
      ↓
Fill CSV
      ↓
Upload CSV
      ↓
Parse Rows
      ↓
Validate
      ↓
Detect Duplicates
      ↓
Preview Results
      ↓
Import Valid Rows
      ↓
Show Summary
```

Do not immediately import on file upload.

Always show a preview first.

---

# 10. CSV Template

Required headers:

```csv
company_name,website,domain,industry,country,state,city,contact_name,job_title,email,phone,linkedin_url,icp,priority
```

Example:

```csv
company_name,website,domain,industry,country,state,city,contact_name,job_title,email,phone,linkedin_url,icp,priority
ABC Logistics Sdn Bhd,https://abc.com,abc.com,Logistics,Malaysia,Selangor,Klang,John Tan,Operations Manager,john@abc.com,+60123456789,,LOGISTICS_HAULAGE,HIGH
Mega Transport,,,,Malaysia,Selangor,Klang,,,,,,LOGISTICS_HAULAGE,
```

---

# 11. CSV Required and Optional Fields

Required:

```text
company_name
icp
```

Optional:

```text
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
priority
```

Blank priority must become:

```text
MEDIUM
```

---

# 12. ICP Values

Accepted CSV values:

```text
LOGISTICS_HAULAGE
PASSENGER_TRANSPORT
COMMERCIAL_ENTERPRISE
```

Human labels may be:

```text
Logistics / Haulage
Passenger Transport
Commercial / Enterprise Fleet
```

CSV should use the stable code values.

---

# 13. Priority Values

Accepted:

```text
LOW
MEDIUM
HIGH
```

Blank:

```text
MEDIUM
```

Invalid values should become row errors.

---

# 14. CSV Row Validation

Each row should be classified as:

```text
READY
DUPLICATE
NEEDS_REVIEW
INVALID
```

Examples:

```text
READY
→ company_name present
→ valid ICP
→ optional fields valid

DUPLICATE
→ existing active lead for same company + ICP

NEEDS_REVIEW
→ possible ambiguous company match

INVALID
→ missing company_name
→ missing/invalid ICP
→ invalid priority
→ malformed email if provided
```

---

# 15. CSV Preview

Example:

| Row | Company | Contact | ICP | Priority | Result |
|---:|---|---|---|---|---|
| 1 | ABC Logistics | John Tan | Logistics | HIGH | Ready |
| 2 | XYZ Transport | — | Logistics | MEDIUM | Ready |
| 3 | ABC Logistics | Sarah Lim | Logistics | MEDIUM | Duplicate |
| 4 | Mega Bus | Kumar | — | MEDIUM | Needs Review |

Summary:

```text
92 Ready
5 Duplicates
3 Need Review
```

Actions:

```text
[ Cancel ]
[ Download Error Rows ]
[ Import Ready Rows ]
```

---

# 16. CSV Import Behavior

For each valid row:

```text
1. Resolve Company
2. Create Company if needed
3. Resolve/Create Contact if contact data exists
4. Create Lead
5. Lead starts as DISCOVERED
```

Rows should be processed independently.

One bad row should not fail the entire file.

Final summary example:

```text
Imported: 92
Skipped Duplicates: 5
Failed: 3
```

---

# 17. PostgreSQL Field Mapping

Do NOT add all import fields directly to the `leads` table.

Use normalized existing tables.

## Companies

```text
company_name  → companies.name
website       → companies.website
domain        → companies.domain
industry      → companies.industry
country       → companies.country
state         → companies.state
city          → companies.city
```

## Contacts

```text
contact_name  → contacts.name
job_title     → contacts.job_title
email         → contacts.email
phone         → contacts.phone
linkedin_url  → contacts.linkedin_url
```

## Leads

```text
icp       → leads.icp_profile_id
priority  → leads.priority
```

Leads also continue using:

```text
company_id
primary_contact_id
```

---

# 18. Nullability Target

## Companies

```text
companies.name        REQUIRED
companies.website     NULLABLE
companies.domain      NULLABLE
companies.industry    NULLABLE
companies.country     NULLABLE
companies.state       NULLABLE
companies.city        NULLABLE
```

## Contacts

Recommended target:

```text
contacts.name         NULLABLE
contacts.job_title    NULLABLE
contacts.email        NULLABLE
contacts.phone        NULLABLE
contacts.linkedin_url NULLABLE
```

However:

```text
do not create an empty Contact row
```

At least one meaningful contact field must exist.

## Leads

```text
leads.company_id          REQUIRED
leads.icp_profile_id      REQUIRED
leads.primary_contact_id  NULLABLE
leads.priority            NOT NULL with default MEDIUM preferred
```

Blank CSV priority should map to:

```text
MEDIUM
```

rather than storing NULL.

---

# 19. Migration 007 Decision

Do NOT automatically create migration `007`.

First inspect:

```text
Company SQLAlchemy model
Contact SQLAlchemy model
Lead SQLAlchemy model

live PostgreSQL:
companies
contacts
leads

alembic current
alembic check
```

Only create:

```text
007
```

if a real schema change is required.

Examples:

```text
contacts.name currently NOT NULL
→ may need DROP NOT NULL

missing company optional column
→ may need ADD COLUMN

missing contact optional column
→ may need ADD COLUMN
```

If schema already supports the target:

```text
NO MIGRATION REQUIRED
```

---

# 20. Existing Duplicate Rules — MUST PRESERVE

Company duplicate detection includes:

```text
domain
normalized company name
website
```

Lead duplicate rule:

```text
one active lead per:
company_id + icp_profile_id
```

Existing Contact duplicate rules remain authoritative.

Business Card and CSV imports must use these same rules.

---

# 21. Duplicate Handling — Business Card

If extracted company matches an existing company:

```text
Possible Existing Company Found
```

Show:

```text
Existing:
ABC Logistics Sdn Bhd
abc.com

[ Use Existing Company ]
[ Review Details ]
```

Do not silently create a duplicate company.

---

# 22. Duplicate Handling — CSV

Possible outcomes:

```text
Exact company match
→ reuse existing company

Active lead for same company + ICP
→ mark DUPLICATE

Possible ambiguous company match
→ mark NEEDS_REVIEW
```

Do not bypass duplicate checks for bulk imports.

---

# 23. Dashboard Navigation

Recommended:

```text
Overview

Leads
├── All Leads
├── Add Lead
└── Import Leads

Marketing Actions
Approvals
System
```

`Import Leads` contains:

```text
Business Card
CSV Upload
```

No AI Discovery section in this build.

---

# 24. Import Leads Page

Suggested route:

```text
/leads/import
```

Tabs:

```text
Business Card
CSV Upload
```

---

# 25. Business Card Route Suggestions

Potential dashboard routes:

```text
GET  /leads/import/card
POST /leads/import/card/extract
POST /leads/import/card/create
```

The dashboard backend should call OCR/Vision and existing Marketing API endpoints server-side.

Do not expose OCR provider credentials to the browser.

---

# 26. CSV Route Suggestions

Potential dashboard routes:

```text
GET  /leads/import/csv
GET  /leads/import/csv/template
POST /leads/import/csv/preview
POST /leads/import/csv/commit
```

---

# 27. Upload Security

Treat uploads as untrusted input.

Business Card:

```text
allow image formats only
validate MIME type
limit file size
generate safe server-side filename
do not trust original filename
do not execute uploaded files
```

CSV:

```text
allow CSV only
limit file size
limit row count
validate encoding
validate headers
validate every row
```

Never expose:

```text
Marketing API key
OCR/Vision provider key
database credentials
```

to browser JavaScript.

---

# 28. Suggested MVP1 Upload Limits

```text
Business Card:
max 10 MB
JPG / JPEG / PNG / WEBP

CSV:
max 5 MB
max 5,000 rows
UTF-8 preferred
```

These may be adjusted later.

---

# 29. OCR / Vision Failure Handling

If extraction fails:

```text
Could not confidently read this card.
Please enter the information manually.
```

Open the autofill form with whatever fields were detected, or blank if necessary.

Do not block manual completion.

---

# 30. Confidence Handling

If extraction confidence is available, it may be shown as a UI hint:

```text
Email     High confidence
Company   High confidence
Phone     Medium confidence
Job Title Low confidence
```

Do not auto-reject solely based on confidence.

---

# 31. CSV Error Reporting

Examples:

```text
Row 3: company_name is required
Row 8: invalid ICP code
Row 10: priority must be LOW, MEDIUM, or HIGH
Row 14: invalid email format
Row 22: duplicate active lead
```

Provide downloadable rejected/error rows if practical.

---

# 32. Lead Lifecycle

Imported leads must enter:

```text
DISCOVERED
```

Then continue through the existing pipeline:

```text
DISCOVERED
   ↓
RESEARCHING
   ↓
QUALIFIED
   ↓
READY_FOR_OUTREACH
   ↓
CONTACTED
   ↓
REPLIED
   ↓
CONVERTED
```

Terminal:

```text
DISQUALIFIED
LOST
```

Do not create a separate lifecycle for imported leads.

---

# 33. n8n Relationship

After import:

```text
Business Card / CSV
        ↓
Company + Contact + Lead
        ↓
Lead = DISCOVERED
        ↓
n8n
        ↓
Research
        ↓
Scoring
        ↓
Product Matching
        ↓
Marketing Action
        ↓
Approval
```

Import logic should not perform research/scoring itself.

---

# 34. No Separate Lead Type

Do not create:

```text
business_card_lead
csv_lead
```

Once confirmed/imported, these are normal Leads.

---

# 35. Recommended Build Order

```text
1. Inspect company/contact/lead schemas
2. Inspect live DB nullability
3. Decide whether migration 007 is required
4. Lock CSV template
5. Build CSV template download
6. Build CSV parser + validator
7. Build CSV preview
8. Build CSV import execution
9. Build Business Card upload UI
10. Add OCR/Vision extraction
11. Build smart autofill review form
12. Reuse Company/Contact/Lead API calls
13. Add duplicate handling
14. Add upload security
15. Add validation tests
16. Run full regression
```

---

# 36. Validation Requirements

## Database

```text
optional company fields accept NULL
optional contact fields accept NULL
primary_contact_id remains nullable
priority defaults correctly
existing data not broken
alembic check clean
```

## Business Card

```text
valid image uploads
unsupported file rejected
oversized file rejected
OCR extraction works
missing fields remain blank
form editable
company required
ICP required
priority defaults MEDIUM
contact omitted if empty
lead created DISCOVERED
duplicate company handled
duplicate lead handled
```

## CSV

```text
template downloads
correct headers accepted
missing required headers rejected
required values validated
optional values may be blank
invalid ICP rejected
invalid priority rejected
blank priority becomes MEDIUM
duplicate active lead detected
preview works
valid rows import
invalid rows do not import
summary counts correct
new leads start DISCOVERED
```

## Architecture

```text
dashboard does not access PostgreSQL directly
imports use Marketing API
API authentication remains enforced
secrets stay server-side
existing duplicate rules remain active
```

---

# 37. Definition of Done

```text
Business Card upload works                       ✓
OCR/Vision smart autofill works                  ✓
Parimala can correct extracted data              ✓
Company + ICP required                           ✓
Optional company fields nullable                 ✓
Optional contact fields nullable                 ✓
Empty contacts are not created                   ✓
Lead created as DISCOVERED                       ✓

CSV template available                           ✓
CSV upload works                                 ✓
CSV preview works                                ✓
Required fields enforced                         ✓
Optional fields allow blank                      ✓
Priority defaults MEDIUM                         ✓
Duplicates identified                            ✓
Valid rows import                                ✓
Invalid rows are reported                        ✓

Existing API rules preserved                     ✓
No direct DB writes from dashboard               ✓
Full regression validation passes                ✓
```

---

# 38. Final Locked Requirements

```text
Business Card
→ Smart Autofill
→ Human Review
→ Existing APIs

CSV
→ Bulk Import
→ company_name + icp required
→ website/domain/industry/country/state/city optional
→ contact_name/job_title/email/phone/linkedin_url optional
→ priority optional
→ blank priority = MEDIUM

Database
→ optional fields nullable where appropriate
→ company name remains required
→ ICP remains required
→ primary contact remains optional
→ no empty Contact rows

Architecture
→ Dashboard → Marketing API → PostgreSQL
→ never Dashboard → PostgreSQL
```

---

# 39. Immediate Next Task for Builder

Start by inspecting the current:

```text
Company model/schema
Contact model/schema
Lead model/schema
live PostgreSQL table definitions
```

Then determine:

```text
Migration 007 required?
YES / NO
```

Do not create migration `007` until an actual schema difference is confirmed.
