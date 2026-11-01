> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Marketing API — Scoring API Status

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**API Module:** Scoring API  
**Status:** COMPLETE  
**Validation Result:** PASSED  
**Current Alembic Head:** `d62d40479f83`  
**Next Migration ID (when actually needed):** `005`  
**Next Stage:** Product Matching API  

---

# 1. Current Status

The MVP1 Scoring API is implemented and validated.

```text
Scoring API
├── Database model/constraints       ✓
├── POST score                       ✓
├── Score history                    ✓
├── Current score endpoint           ✓
├── Score detail endpoint            ✓
├── Current-score replacement        ✓
├── leads.current_score sync         ✓
├── Research eligibility             ✓
├── Range/schema validation          ✓
├── Event logging                    ✓
├── Qualification deferred           ✓
├── Automated validation             ✓
└── MVP1 Scoring API                 COMPLETE
```

No database migration was required for the Scoring API because the existing schema already supported all required MVP1 mechanics.

---

# 2. Architecture Preserved

The required architecture remains unchanged:

```text
n8n
  │
  │ HTTP / JSON
  ▼
Marketing API
  │
  │ SQLAlchemy / psycopg
  ▼
PostgreSQL
```

Rules preserved:

```text
n8n       ✕ PostgreSQL
Dashboard ✕ PostgreSQL
Internet  ✕ PostgreSQL

Marketing API ✓ PostgreSQL
```

The Marketing API continues to own:

```text
validation
business rules
research lifecycle
scoring logic
current-score management
qualification logic
event logging
database access
```

n8n integration has NOT been started.

---

# 3. Existing Database Support

The existing `lead_scores` table already contained:

```text
id
lead_id
total_score
score_breakdown
scoring_version
rationale
is_current
created_at
```

Existing database protections:

```text
total_score BETWEEN 0 AND 100
```

Indexes:

```text
idx_lead_scores_lead_id
idx_lead_scores_one_current
```

The current-score index is:

```text
UNIQUE (lead_id)
WHERE is_current = TRUE
```

This guarantees a maximum of one current score per lead.

The `leads` table already contains:

```text
current_score
```

No schema changes were necessary.

---

# 4. Alembic Status

Before implementation:

```text
alembic check
→ No new upgrade operations detected.
```

Because the existing scoring schema was sufficient:

```text
No Scoring migration was created.
```

The current Alembic head remains:

```text
d62d40479f83
```

The already-applied Research migration is treated conceptually as migration `004`.

Future migrations must use explicit sequential IDs:

```text
005
006
007
...
```

Do not generate another random Alembic revision ID.

Do not create migration `005` unless a real schema change is required.

---

# 5. Implemented Files

Added:

```text
api/app/schemas/scoring.py
api/app/services/scoring_service.py
api/app/routers/scoring.py
api/scripts/validate_scoring_api.py
```

Updated:

```text
api/app/main.py
```

The Scoring router was added without removing or replacing the existing:

```text
Health
Companies
Contacts
Leads
Research
```

routers.

---

# 6. Implemented Routes

The following routes are registered:

```text
POST /api/leads/{lead_id}/scores
GET  /api/leads/{lead_id}/scores

GET  /api/leads/{lead_id}/scores/current

GET  /api/scoring/{score_id}
```

OpenAPI verification passed for all Scoring routes.

---

# 7. Score Creation Rules

Target:

```text
POST /api/leads/{lead_id}/scores
```

Implemented behavior:

```text
validate lead exists
reject terminal lead statuses
require usable research
validate score input
lock lead row using SELECT ... FOR UPDATE
find current score
set previous current score FALSE
insert new score TRUE
update leads.current_score
write lead_scored event
commit atomically
```

If any transaction step fails:

```text
ROLLBACK
```

The current score replacement is protected by both:

```text
service-level lead row locking
+
database unique partial index
```

---

# 8. Score History

Every valid score submission creates a new `lead_scores` row.

Historical scores are never overwritten.

Verified behavior:

```text
Score 1 → current
Score 2 created
    ↓
Score 1 → is_current = FALSE
Score 2 → is_current = TRUE
```

Score history endpoint:

```text
GET /api/leads/{lead_id}/scores
```

returns all score rows newest first.

---

# 9. Lead Current Score Synchronization

Required invariant:

```text
current LeadScore.total_score
=
leads.current_score
```

This has been implemented and verified.

Manual validation confirmed:

```text
Current LeadScore.total_score = 86
leads.current_score = 86
```

Automated validation later confirmed the same invariant after additional score replacement.

---

# 10. Current Score Endpoint

Route:

```text
GET /api/leads/{lead_id}/scores/current
```

Behavior:

```text
current score exists → 200
no current score     → 404
```

The returned score must have:

```text
is_current = TRUE
```

and must match:

```text
leads.current_score
```

---

# 11. Score Detail Endpoint

Route:

```text
GET /api/scoring/{score_id}
```

Behavior:

```text
score exists  → 200
score missing → 404
```

Verified by automated validation.

---

# 12. Research Eligibility

Scoring is intentionally separated from Research.

Required flow:

```text
Lead
  ↓
Research
  ↓
COMPLETED or PARTIAL
  ↓
Scoring
```

MVP1 eligibility implemented:

```text
At least one Research run with status:
COMPLETED
or
PARTIAL
```

Not usable for scoring:

```text
PENDING
RUNNING
FAILED
```

The service selects the newest usable research run ordered by:

```text
completed_at DESC
created_at DESC
```

The current `lead_scores` schema does NOT contain a `research_id` FK.

For MVP1:

```text
No research_id was added.
```

Exact research provenance can be revisited later if required.

---

# 13. Terminal Lead Safety

The current Scoring service rejects scoring for terminal lead statuses:

```text
CONVERTED
DISQUALIFIED
LOST
```

Rescoring terminal leads is not yet an approved business rule.

---

# 14. Qualification Policy

Qualification is intentionally deferred.

The project still does NOT define:

```text
exact scoring formula
category weights
qualification threshold
hard disqualification rules
human override policy
rescoring rules for terminal leads
```

Therefore Scoring currently updates:

```text
lead_scores
leads.current_score
events
```

but does NOT automatically change:

```text
lead.status
```

Verified behavior:

```text
lead remained RESEARCHING after scoring
```

Research completion still does not automatically qualify the lead.

No threshold such as:

```text
>= 50
>= 60
>= 70
```

has been assumed.

---

# 15. Scoring Input

Current controlled score-submission contract:

```json
{
  "total_score": 78,
  "score_breakdown": {
    "country_fit": 10,
    "industry_fit": 20,
    "fleet_size": 18,
    "decision_maker": 10,
    "buying_signal": 12,
    "product_fit": 8
  },
  "scoring_version": "mvp1-v1",
  "rationale": "Strong ICP and fleet fit with multiple buying signals."
}
```

Required input rules:

```text
total_score        → integer 0–100
score_breakdown    → JSON object
scoring_version    → required, non-empty, non-blank
rationale          → required by MVP1 API, non-empty, non-blank
```

---

# 16. Event Logging

Minimum scoring event implemented:

```text
lead_scored
```

Event metadata includes:

```json
{
  "lead_id": "...",
  "score_id": "...",
  "total_score": 78,
  "scoring_version": "mvp1-v1",
  "previous_score": null
}
```

On rescoring:

```json
{
  "previous_score": 78
}
```

is recorded.

Manual event verification passed.

Automated event verification also passed.

Qualification events such as:

```text
lead_qualified
lead_disqualified
```

are not generated yet because qualification policy is deferred.

---

# 17. Manual Validation

Manual score run 1:

```text
Score ID:
8c2ca31b-c916-496c-9b6d-6bce7c2316fb

total_score:
78

scoring_version:
mvp1-v1

is_current:
TRUE
```

Manual score run 2:

```text
Score ID:
2d9d8f0c-3147-4102-841f-91b11780b4e4

total_score:
86

scoring_version:
mvp1-v2-test

is_current:
TRUE
```

After score run 2:

```text
Score 78 → is_current = FALSE
Score 86 → is_current = TRUE
leads.current_score = 86
lead.status = RESEARCHING
```

PostgreSQL confirmed exactly one current score.

Manual `lead_scored` event verification also passed.

---

# 18. Negative Validation

Manual negative-path validation:

```text
PASS: 9
FAIL: 0
```

Verified:

```text
total_score = -1            → 422
total_score = 101           → 422
empty scoring_version       → 422
blank scoring_version       → 422
empty rationale             → 422
blank rationale             → 422
missing scoring_version     → 422
nonexistent lead            → 404
nonexistent score           → 404
```

---

# 19. Automated Validation

Validation script:

```text
api/scripts/validate_scoring_api.py
```

Final automated validation result:

```text
PASS: 58
FAIL: 0
SKIP: 2

RESULT: PASSED
```

The validator created two additional score rows:

```text
6436c69a-0fff-446b-8891-86303ee09ff8
4dcb6f79-b221-41d6-b43e-7130dde53d99
```

Validation score sequence:

```text
Run A → 73
Run B → 87
```

Final validated current score:

```text
87
```

Automated validation confirmed:

```text
OpenAPI routes
database columns
database constraints
history index
one-current-score unique partial index
404 behavior
422 behavior
research eligibility
score creation
score detail retrieval
current score endpoint
score replacement
score history
newest-first ordering
leads.current_score synchronization
exactly one current score in PostgreSQL
lead status remains unchanged
lead_scored event creation
event score references
event previous_score behavior
```

---

# 20. Expected Validation Skips

Two checks were skipped:

```text
No usable research -> 409
No current score -> 404
```

Reason:

```text
The database currently has only one lead.
That lead already has usable Research and current Score history.
```

Validator result:

```text
[SKIP] No usable research -> 409
[SKIP] No current score -> 404
```

These are expected environment skips, not implementation failures.

The validator supports these tests later using:

```text
--unresearched-lead-id <uuid>
--no-score-lead-id <uuid>
```

---

# 21. Current Test Lead

Lead:

```text
dcb7d435-cf8c-4202-868f-3666dc53f8ac
```

Current status after Scoring validation:

```text
RESEARCHING
```

Current score after automated validation:

```text
87
```

The status correctly remains `RESEARCHING` because qualification is deferred.

---

# 22. Confirmed Invariants

The following Scoring invariants are now proven:

```text
Every score creates history                          ✓
Previous score rows are preserved                    ✓
Only one current score exists                        ✓
New score becomes current                            ✓
Previous current score becomes non-current           ✓
leads.current_score matches current LeadScore        ✓
Score replacement is atomic                          ✓
lead_scored event is written                         ✓
Previous score is recorded in event metadata         ✓
Scoring does not automatically qualify a lead        ✓
Research and Scoring remain separate                 ✓
n8n remains isolated from PostgreSQL                 ✓
```

---

# 23. Scoring API Completion State

Final state:

```text
Companies            ✓
Contacts             ✓
Leads                ✓
Research             ✓
Scoring              ✓
    ↓
Product Matching     NEXT
    ↓
Marketing Actions
    ↓
Approvals
    ↓
n8n Integration
```

The Scoring API is complete for the current MVP1 scope.

---

# 24. Next Stage

Next authoritative development stage:

```text
Product Matching API
```

Do NOT:

```text
rebuild Scoring
add qualification threshold without approval
add research_id silently
integrate n8n yet
create an empty migration 005
```

Before Product Matching implementation:

```text
inspect current ProductMatch model
inspect current product catalog/model
inspect PostgreSQL indexes/constraints
run alembic check
define Product Matching business rules
```

---

# 25. Continuation Note

Continue from the existing implementation.

Do not recreate:

```text
PostgreSQL deployment
Docker networks
FastAPI foundation
SQLAlchemy base
Alembic setup
Companies API
Contacts API
Leads API
Research API
Research Sources API
Scoring API
Scoring validation
```

Current Scoring API status:

```text
MVP1 COMPLETE
PASS: 58
FAIL: 0
SKIP: 2
RESULT: PASSED
```

Proceed next to:

```text
Product Matching API
```
