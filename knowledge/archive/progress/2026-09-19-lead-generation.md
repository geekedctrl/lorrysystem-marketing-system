> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem AI Marketing & Lead Generation — Progress Log

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1 / Lead Generation + Dashboard V2  
**Status Date:** 2026-09-19  
**Environment:** Self-hosted DietPi / Docker / PostgreSQL / FastAPI / n8n

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

Dashboard path:

```text
Browser
  │ HTTP/HTTPS
  ▼
Dashboard/BFF (FastAPI + Jinja2)
  │ server-side X-API-Key
  ▼
Marketing API
  ▼
PostgreSQL
```

### Security Boundary

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

## 2. Backend Status

Completed and verified:

- Marketing API business layer
- PostgreSQL persistence layer
- Companies
- Contacts
- Leads
- Research
- Scoring
- Product Matching
- Marketing Actions
- Approval API
- Database integrity rules
- X-API-Key protection for `/api/*`
- Open `/health` endpoint

Current Alembic database head:

```text
007
```

---

## 3. Migration 007 — Contact Name Optional

Migration 007 was created and successfully applied.

### Behaviour

`contacts.full_name` is now nullable.

A Contact may be created without a name when another meaningful contact field is present.

Accepted meaningful fields include:

- full_name
- job_title
- email
- phone
- linkedin_url

An entirely empty Contact is rejected.

### Verified Result

```text
PASS: 5
FAIL: 0
RESULT: PASSED
```

Verified:

- ContactCreate accepts contact without full_name
- Empty contact is rejected
- full_name is not required in OpenAPI
- SQLAlchemy model is nullable
- Alembic head is 007

---

## 4. Lead Import V2

Two lead intake methods are now supported.

### Business Card Import

Flow:

```text
Upload Image
    ↓
OCR
    ↓
Extract fields
    ↓
Editable review
    ↓
Select ICP / priority
    ↓
Create Company / Contact / Lead
```

Fields attempted during extraction:

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

Rules:

- company_name required
- ICP required
- priority defaults to MEDIUM
- Contact name is optional if another meaningful contact field exists
- No empty Contact row is created
- Existing company matches are surfaced instead of silently duplicated

Supported image types:

```text
JPG
JPEG
PNG
WEBP
```

Suggested maximum image size:

```text
10 MB
```

---

## 5. CSV Lead Import

CSV headers:

```csv
company_name,website,domain,industry,country,state,city,contact_name,job_title,email,phone,linkedin_url,icp,priority
```

Required:

```text
company_name
icp
```

Default:

```text
priority = MEDIUM
```

Preview classifications:

```text
READY
DUPLICATE
NEEDS_REVIEW
INVALID
```

Imports are previewed before commit.

Suggested limits:

```text
Maximum CSV size: 5 MB
Maximum rows: 5,000
Encoding: UTF-8
```

Imported Leads begin as:

```text
DISCOVERED
```

Imports do not directly perform research or scoring. n8n handles later pipeline stages.

---

## 6. Duplicate Detection

Company duplicate checks use:

- domain
- normalized company name
- website

Lead duplicate checks use:

```text
company_id + icp_profile_id
```

for an existing active Lead.

Contact duplicate behaviour follows the existing Marketing API rules.

---

## 7. API Pagination

Offset pagination was added to:

```text
GET /api/companies
GET /api/contacts
GET /api/leads
```

Supported parameters:

```text
limit
offset
```

OpenAPI verification confirmed:

```text
/api/companies → limit, offset
/api/contacts  → company_id, limit, offset
/api/leads     → company_id, status, priority, limit, offset
```

This allows the Dashboard to safely process datasets larger than 100 records without direct PostgreSQL access.

---

## 8. Dashboard V2

Dashboard location:

```text
/opt/lorrysystem-dashboard
```

Current pages:

```text
/dashboard
/leads
/leads/new
/leads/{id}
/approvals
/approvals/{id}
/actions
/system
/health
```

Implemented features:

- overview dashboard
- Lead listing and filtering
- manual Add Lead
- detailed Lead pipeline view
- approval decision flow
- system status page
- server-side Marketing API authentication
- session middleware
- CSRF protection
- reviewer identity
- Business Card import
- CSV import preview
- CSV commit
- duplicate detection
- downloadable error-row CSV
- paginated API reads

The Dashboard does not access PostgreSQL directly.

---

## 9. Import Regression Test

Dashboard import validator result:

```text
PASS: 18
FAIL: 0
RESULT: PASSED
```

Verified:

- import page loads
- CSV template downloads
- CSV headers are correct
- invalid Business Card MIME rejected
- valid card reaches review page
- Business Card fields are editable
- CSV preview works
- blank priority becomes MEDIUM
- valid row becomes READY
- commit succeeds
- imported Lead starts DISCOVERED
- duplicate row detected
- error-row CSV download works
- exported error row contains DUPLICATE
- invalid row detected
- Contact without name path works

---

## 10. Validator Authentication Fix

After X-API-Key security was introduced, the older deep module validators were receiving HTTP 401 responses because they did not send the API key.

Updated validators:

```text
validate_approval_api.py
validate_marketing_actions_api.py
validate_product_matching_api.py
validate_research_api.py
validate_scoring_api.py
```

Each validator now reads one of:

```text
MARKETING_API_KEY
API_KEY
LORRYSYSTEM_API_KEY
```

and sends:

```http
X-API-Key: <configured key>
```

This preserved API security instead of weakening authentication for testing.

---

## 11. Full Regression Result

Final deep regression:

```text
PASS: 109
FAIL: 0
SKIP: 0

RESULT: PASSED
```

Stage results:

```text
PRECHECK             PASSED
ROUTES               PASSED
DATABASE             PASSED
FOUNDATION           PASSED
RESEARCH             PASSED
SCORING              PASSED
PRODUCT_MATCHING     PASSED
MARKETING_ACTIONS    PASSED
APPROVAL             PASSED
CROSS_STAGE          PASSED
EVENTS               PASSED
DEEP                 PASSED
```

Deep validators also passed individually:

```text
Approval API             PASSED
Marketing Actions API    PASSED
Product Matching API     PASSED
Research API             PASSED
Scoring API              PASSED
```

---

## 12. Security Cleanup Performed

A quick cleanup/security pass was completed.

### Backup Cleanup

Temporary `.before-*.bak` files were archived to:

```text
/opt/lorrysystem-backups/pre-security-cleanup-2026-09-19.tar.gz
```

The archived temporary backups were then removed from the application directories.

Backup directory and archive permissions were tightened.

### Sensitive File Permissions

Verified:

```text
600 /opt/lorrysystem-marketing/.env
600 /opt/lorrysystem-dashboard/.env
600 /opt/lorrysystem-backups/pre-security-cleanup-2026-09-19.tar.gz
```

### Marketing API Key Rotation

The previously exposed Marketing API key was rotated.

The new key was updated in:

```text
/opt/lorrysystem-marketing/.env
/opt/lorrysystem-dashboard/.env
n8n Header Auth credential
```

### Dashboard Session Secret Rotation

The Dashboard session secret was rotated.

This intentionally invalidated previous Dashboard sessions.

### Temporary Secret Files

Temporary plaintext secret files were deleted after use.

Verified removed:

```text
/root/lorrysystem-marketing-api-key.next
/root/lorrysystem-dashboard-session.next
```

### `.env.example` Verification

Confirmed that:

```text
MARKETING_API_KEY
DASHBOARD_SESSION_SECRET
```

inside `.env.example` do not match the live values.

---

## 13. API Security Smoke Test

Verified behaviour:

```text
GET /health without API key        → 200
GET /api/companies without key     → 401
GET /api/companies with valid key  → 200
```

This confirms API authentication remains enforced after key rotation.

---

## 14. Dashboard → API Smoke Test

Verified from inside the running Dashboard container:

```text
Dashboard → Marketing API = HTTP 200
```

The Dashboard is successfully using the rotated server-side API key.

---

## 15. Business Card UI Cleanup

Old message:

```text
Current API note: if any contact information is kept,
a contact name is currently required.
```

Updated to:

```text
Contact name is optional when another meaningful contact field
such as email, phone, job title, or LinkedIn URL is provided.
```

The updated text was verified inside the running Dashboard container.

---

## 16. n8n → Marketing API Security Verification

Existing n8n workflow used:

```text
LorrySystem - Test Header Auth Credential
```

Credential:

```text
LorrySystem Marketing API
```

Header:

```text
X-API-Key
```

The Header Auth credential was updated with the rotated Marketing API key.

Final result:

```text
n8n Header Auth → Marketing API ✅ WORKING
```

This completes the application-side secret rotation verification.

---

## 17. n8n Workflows Currently Available

Relevant LorrySystem workflows:

```text
Stage 1 - API Test

LorrySystem - N2 Lead Intake
LorrySystem - N3 Research Orchestration
LorrySystem - N4 Scoring Orchestration
LorrySystem - N5 Product Matching
LorrySystem - N6 Marketing Action Creation
LorrySystem - N7 Approval Orchestration

LorrySystem - MVP1 Full E2E API Test v2
LorrySystem - Test Header Auth Credential
```

---

## 18. Current Overall Status

```text
Backend                              ✅
PostgreSQL                           ✅
Migration 007                        ✅
Contacts nullable-name support       ✅
Large-dataset pagination             ✅
Duplicate detection                  ✅
Business Card import                 ✅
CSV import                           ✅
CSV preview                          ✅
Error-row download                   ✅
Dashboard V2                         ✅
Dashboard → API authentication       ✅
n8n → API authentication             ✅
API security enforcement             ✅
Import regression                    ✅ 18/18
Full deep regression                 ✅ 109/109
Security cleanup                     ✅
Marketing API key rotation           ✅
Dashboard session secret rotation    ✅
```

---

## 19. Intentionally Not Rotated

The following was deliberately left unchanged:

```text
N8N_ENCRYPTION_KEY
```

Reason:

The n8n encryption key protects credentials stored in n8n. Changing it casually can make existing encrypted credentials unreadable.

If it is rotated later, it should be handled as a controlled n8n credential migration rather than a normal environment-secret replacement.

---

## 20. Recommended Next Step

The current Lead Generation / Dashboard foundation is stable.

The next development phase can focus on n8n orchestration for imported Leads:

```text
DISCOVERED
    ↓
RESEARCHING
    ↓
Research
    ↓
Scoring
    ↓
Product Matching
    ↓
Marketing Action Creation
    ↓
Approval
```

A useful next validation is to confirm that a Lead created through either:

```text
Business Card Import
or
CSV Import
```

is picked up by the existing n8n pipeline and processed end-to-end.

---

# Milestone

**Lead Generation + Dashboard V2 + Security Cleanup**

```text
STATUS: COMPLETE
CORE REGRESSION: PASSED
IMPORT REGRESSION: PASSED
API AUTHENTICATION: VERIFIED
DASHBOARD AUTHENTICATION: VERIFIED
N8N HEADER AUTH: VERIFIED
```
