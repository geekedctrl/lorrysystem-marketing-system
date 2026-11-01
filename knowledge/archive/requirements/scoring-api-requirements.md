> Historical record. Original statuses and next-step instructions describe an earlier project state. Use the [current status](../../status/current-status.md) for present implementation and priorities. Preserved and organized on 2026-10-06.

[Knowledge index](../../README.md)
# LorrySystem Marketing API — SCORING API HANDOFF

**Project:** LorrySystem AI Marketing & Lead Generation  
**Stage:** MVP1  
**Current API state:** Companies + Contacts + Leads + Research complete and validated  
**Next authoritative stage:** Scoring API  
**Environment:** `/opt/lorrysystem-marketing` on Docker / DietPi  
**Current Alembic head:** `d62d40479f83`

---

# 1. Purpose

This file is the authoritative handoff for building the **Scoring API**.

The Scoring API comes after Research and before Product Matching.

Build order:

```text
Companies            ✓
Contacts             ✓
Leads                ✓
Research             ✓
    ↓
Scoring              NEXT
    ↓
Product Matching
    ↓
Marketing Actions
    ↓
Approvals
    ↓
n8n Integration
```

Do **not** rebuild completed API modules unless a verified bug requires it.

Do **not** integrate n8n yet.

---

# 2. Architecture Rules — MUST PRESERVE

The architecture remains:

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

Never change this into:

```text
n8n ─────► PostgreSQL
```

Rules:

```text
n8n       ✕ PostgreSQL
Dashboard ✕ PostgreSQL
Internet  ✕ PostgreSQL

Marketing API ✓ PostgreSQL
```

The Marketing API owns:

```text
validation
duplicate protection
lifecycle transitions
research lifecycle
scoring logic
qualification logic
product matching
approval logic
event logging
database access
```

PostgreSQL remains:

```text
persistent storage
+
hard integrity constraints
```

---

# 3. Current Project State

Project root:

```text
/opt/lorrysystem-marketing
```

Existing completed modules:

```text
Companies API
Contacts API
Leads API
Research API
Research Sources API
Research lifecycle
Research events
```

Current Research validation:

```text
PASS: 80
FAIL: 0
SKIP: 1
RESULT: PASSED
```

Research API MVP1 is complete.

---

# 4. Existing LeadScore Database Model

The existing `lead_scores` table is already present.

Current schema:

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

Meaning:

```text
id
= score record UUID

lead_id
= lead being scored

total_score
= integer 0–100

score_breakdown
= JSONB containing category-level scoring details

scoring_version
= scoring algorithm / rules version

rationale
= human-readable explanation of the score

is_current
= whether this score is the currently active score for the lead

created_at
= score creation timestamp
```

The table is intentionally historical.

Do **not** overwrite previous scores.

Correct structure:

```text
Lead
├── Score Run 1
├── Score Run 2
├── Score Run 3
└── ...
```

Only one score should be marked current at a time.

---

# 5. Existing Score Constraints

The current database already enforces:

```text
total_score BETWEEN 0 AND 100
```

The schema also contains:

```text
idx_lead_scores_lead_id
```

and:

```text
idx_lead_scores_one_current
```

The current-score index is a partial unique index:

```text
UNIQUE (lead_id)
WHERE is_current = TRUE
```

Therefore PostgreSQL already enforces:

```text
maximum one current score per lead
```

This rule must be preserved.

---

# 6. Lead Current Score

The `leads` table already contains:

```text
current_score
```

with:

```text
0–100
```

The Scoring API must keep these two concepts synchronized:

```text
lead_scores.is_current = TRUE
        │
        └── total_score
                │
                ▼
       leads.current_score
```

Required invariant:

```text
If a lead has a current LeadScore,
leads.current_score MUST equal
that LeadScore.total_score.
```

The Scoring service should update both in one database transaction.

---

# 7. Score History Rule

Every scoring attempt creates a **new** `lead_scores` row.

Never update the historical score record into a new score.

Correct behavior:

```text
First scoring run
    ↓
Score A
is_current = TRUE

Second scoring run
    ↓
Score A → is_current = FALSE
Score B → is_current = TRUE
leads.current_score = Score B.total_score

Third scoring run
    ↓
Score A → FALSE
Score B → FALSE
Score C → TRUE
leads.current_score = Score C.total_score
```

This preserves score history and scoring-version history.

---

# 8. Example Score Breakdown

The existing schema documentation gives this example:

```json
{
  "country_fit": 10,
  "industry_fit": 20,
  "fleet_size": 18,
  "decision_maker": 10,
  "buying_signal": 15,
  "product_fit": 14
}
```

This is an example structure, not yet a fully defined scoring formula.

The Scoring API must allow structured JSON breakdown storage.

---

# 9. Scoring Version — REQUIRED

Every score must include:

```text
scoring_version
```

Do not create scores without a version.

Examples:

```text
v1
mvp1-v1
2026-09-v1
```

The exact naming convention still needs to be selected during implementation.

Purpose:

```text
historical reproducibility
algorithm comparison
debugging
future rule changes
```

Never silently reuse a score version after materially changing scoring rules.

---

# 10. Rationale

Each score should contain a human-readable:

```text
rationale
```

The schema permits it to be nullable, but the MVP1 API should normally require or generate a rationale so humans can understand the score.

Do not use rationale as the numerical source of truth.

`score_breakdown` remains the structured machine-readable record.

---

# 11. Scoring Input Dependency

Scoring comes **after Research**.

Correct flow:

```text
Lead
    ↓
Research
    ↓
Research COMPLETED or PARTIAL
    ↓
Scoring
```

Research completion does **not** directly qualify a lead.

Correct flow:

```text
Research completed
        ↓
Scoring stage
        ↓
QUALIFIED
or
DISQUALIFIED
```

Qualification remains a Scoring-stage responsibility.

---

# 12. Research Eligibility for Scoring

Recommended MVP1 eligibility:

```text
At least one research run with status:
COMPLETED
or
PARTIAL
```

Do not use:

```text
PENDING
RUNNING
FAILED
```

as the basis for a final qualification score.

If multiple usable research runs exist, define which one is used.

Recommended MVP1 rule:

```text
Use the newest usable research run
ordered by completed_at / created_at.
```

This recommendation is an implementation choice, not an existing source-defined rule.

---

# 13. Lead Lifecycle Integration

Current lead lifecycle:

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

Alternative exits:

```text
DISQUALIFIED
LOST
```

Scoring is the stage responsible for deciding:

```text
RESEARCHING
    ↓
QUALIFIED

or

RESEARCHING
    ↓
DISQUALIFIED
```

Research must never make this decision.

---

# 14. Qualification Threshold — NOT YET DEFINED

The existing project sources do **not** define a qualification threshold.

Do not silently invent one.

Examples that must not be assumed without approval:

```text
>= 50 = QUALIFIED
>= 60 = QUALIFIED
>= 70 = QUALIFIED
```

Before automatic qualification is enabled, explicitly define:

```text
qualification_threshold
```

Possible future configuration:

```text
SCORING_QUALIFICATION_THRESHOLD=70
```

Until the threshold is approved, the Scoring API may:

```text
create/store score
update current score
log lead_scored
```

without automatically changing lead status.

---

# 15. Scoring Formula — NOT YET DEFINED

The existing schema provides an example breakdown but does not define:

```text
exact category weights
exact qualification threshold
exact scoring formula
penalty rules
mandatory criteria
```

Do not invent these as established project requirements.

Separate:

```text
Scoring API mechanics
```

from:

```text
Scoring algorithm policy
```

---

# 16. Recommended MVP1 Scoring Mode

To unblock API development before the final algorithm exists, use a controlled score-submission API.

Example request:

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

The API remains responsible for:

```text
range validation
lead validation
current-score switching
history preservation
leads.current_score synchronization
event logging
qualification transition if policy exists
```

---

# 17. Required Scoring API Routes

Recommended MVP1 routes:

```text
POST /api/leads/{lead_id}/scores
GET  /api/leads/{lead_id}/scores

GET  /api/leads/{lead_id}/scores/current
GET  /api/scoring/{score_id}
```

Optional later:

```text
POST /api/leads/{lead_id}/rescore
```

Do not add a separate rescore endpoint unless it truly has different behavior from creating a new score.

---

# 18. POST Score Requirements

Target:

```text
POST /api/leads/{lead_id}/scores
```

Must:

```text
validate lead exists
validate total_score 0–100
validate score_breakdown is an object
validate scoring_version exists
preserve previous score rows
set old current score(s) FALSE
insert new score TRUE
update leads.current_score
write lead_scored event
commit atomically
return created score
```

Critical:

```text
Changing is_current
+
creating the new score
+
updating leads.current_score
+
event logging
```

must occur in the same transaction.

---

# 19. List Score History

Target:

```text
GET /api/leads/{lead_id}/scores
```

Return all score records for the lead.

Recommended ordering:

```text
newest first
```

History must never be overwritten.

---

# 20. Current Score Route

Target:

```text
GET /api/leads/{lead_id}/scores/current
```

Behavior:

```text
current score exists → HTTP 200
no current score     → HTTP 404
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

# 21. Score Detail Route

Target:

```text
GET /api/scoring/{score_id}
```

Behavior:

```text
score exists  → HTTP 200
score missing → HTTP 404
```

---

# 22. Scoring Schemas

Recommended file:

```text
api/app/schemas/scoring.py
```

Request:

```text
ScoreCreate
```

Fields:

```text
total_score
score_breakdown
scoring_version
rationale
```

Response:

```text
ScoreRead
```

Fields:

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

Do not add qualification response fields until qualification policy is finalized.

---

# 23. Scoring Service

Recommended file:

```text
api/app/services/scoring_service.py
```

Responsibilities:

```text
validate lead
validate scoring eligibility
select research context if required
create score
preserve score history
switch previous current score to false
set new score current
sync leads.current_score
apply lifecycle policy if configured
log events
return score
```

Recommended exceptions:

```text
ScoringLeadNotFoundError
ScoringNotAllowedError
CurrentScoreNotFoundError
ScoreNotFoundError
InvalidScoreError
```

---

# 24. Scoring Router

Recommended file:

```text
api/app/routers/scoring.py
```

Recommended HTTP mappings:

```text
lead not found          → 404
score not found         → 404
current score not found → 404
invalid score input     → 422
lead not eligible       → 409
```

Avoid generic `500` responses for expected business-rule failures.

---

# 25. Event Logging

The existing event examples include:

```text
lead_scored
lead_qualified
```

Minimum scoring event:

```text
lead_scored
```

Recommended metadata:

```json
{
  "lead_id": "...",
  "score_id": "...",
  "total_score": 78,
  "scoring_version": "mvp1-v1",
  "previous_score": 64
}
```

If scoring later changes the lead to QUALIFIED:

```text
lead_qualified
```

should also be logged.

If a future scoring policy changes the lead to DISQUALIFIED, use a clear event such as:

```text
lead_disqualified
```

`event_type` is TEXT, so this does not inherently require a schema migration.

---

# 26. Atomic Current-Score Replacement

Critical transaction:

```text
BEGIN

1. Find current score
2. Set current score is_current = FALSE
3. Insert new score is_current = TRUE
4. Set leads.current_score = new total_score
5. Add lead_scored event
6. Apply status transition if configured

COMMIT
```

If any step fails:

```text
ROLLBACK
```

Never commit an intermediate state.

---

# 27. Concurrent Scoring Protection

The database already enforces:

```text
only one is_current = TRUE per lead
```

through:

```text
idx_lead_scores_one_current
```

The service should handle concurrency cleanly.

Recommended implementation consideration:

```text
SELECT ... FOR UPDATE
```

on the lead before replacing the current score.

This is recommended protection, not a pre-existing project requirement.

---

# 28. Database Migration Requirements

A new migration is needed **only if the existing scoring model/schema must change**.

Current schema already supports:

```text
score history
0–100 score
JSONB breakdown
scoring version
rationale
current flag
one current score
lead current score
```

Before creating another migration:

```bash
docker exec lorrysystem-marketing-api alembic check
```

If no model changes are needed:

```text
do not create an empty migration
```

If changes are required, create the next migration after:

```text
d62d40479f83
```

Do not edit already-applied migrations.

---

# 29. Scoring and Research Relationship

Research is historical:

```text
Research Run 1
Research Run 2
Research Run 3
```

Scoring is also historical:

```text
Score Run 1
Score Run 2
Score Run 3
```

The current schema does **not** contain:

```text
research_id
```

inside `lead_scores`.

Therefore the existing sources do not establish a direct FK between a score and the exact research run used.

Architecture decision to review:

```text
A. Keep current schema for MVP1
   Score belongs only to lead.

B. Add research_id to lead_scores
   Exact research provenance is explicit.
```

Do not silently add `research_id`.

---

# 30. Qualification Policy — DECISION REQUIRED

The project establishes:

```text
Research completed
    ↓
Scoring
    ↓
QUALIFIED or DISQUALIFIED
```

but does not define the numerical threshold or exact policy.

Decisions still required:

```text
What score qualifies?
Are there hard disqualification rules?
Can PARTIAL research be scored?
Does research confidence affect score?
Can a human override qualification?
Can rescoring reopen a DISQUALIFIED lead?
```

These are unresolved business-policy decisions.

---

# 31. Recommended MVP1 Lifecycle Safety Rule

Until qualification policy is finalized:

```text
Scoring may update:
lead_scores
leads.current_score
events

Scoring should NOT automatically mutate:
lead.status
```

Once threshold/rules are approved:

```text
RESEARCHING
    ↓
score policy
    ├── QUALIFIED
    └── DISQUALIFIED
```

and lifecycle events/timestamps should be updated atomically.

---

# 32. Product Matching Relationship

Product Matching is the next stage after Scoring.

Current example score breakdown includes:

```text
product_fit
```

but Product Matching has its own table:

```text
product_matches
```

Keep these concepts separate:

```text
Scoring
= overall lead qualification / prioritization

Product Matching
= which LorrySystem products fit the lead
```

Do not merge Product Matching into the Scoring API prematurely.

---

# 33. Scoring API Validation Requirements

Before Scoring API is complete, validate:

```text
Cannot score nonexistent lead
total_score < 0 rejected
total_score > 100 rejected
Missing scoring_version rejected
Score history is preserved
First score becomes current
Second score makes first non-current
Only one current score remains
leads.current_score matches current LeadScore
Score list is newest first
Current-score endpoint returns current score
Unknown score returns 404
No current score returns 404
lead_scored event is written
Event references correct lead/score
Database one-current-score protection holds
Current-score replacement is atomic
```

If research eligibility is enforced:

```text
No usable research → rejected
COMPLETED research → accepted
PARTIAL research → according to chosen policy
FAILED-only research → rejected
```

If automated qualification is implemented:

```text
threshold boundary works
QUALIFIED transition correct
DISQUALIFIED transition correct
research completion still does not auto-qualify
qualified_at timestamp correct
lifecycle events correct
```

---

# 34. Automated Validation Script

Create:

```text
api/scripts/validate_scoring_api.py
```

It should test:

```text
API routes
score creation
score history
current-score switching
lead current-score synchronization
range validation
404 behavior
409 behavior
event logging
database invariants
qualification behavior if enabled
```

Output:

```text
PASS
FAIL
SKIP
RESULT
```

similar to the Research validation script.

---

# 35. Suggested API Contract

Create request:

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

Response:

```json
{
  "id": "<score-uuid>",
  "lead_id": "<lead-uuid>",
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
  "rationale": "Strong ICP and fleet fit with multiple buying signals.",
  "is_current": true,
  "created_at": "<timestamp>"
}
```

---

# 36. Recommended Implementation Files

Add:

```text
api/app/schemas/scoring.py
api/app/services/scoring_service.py
api/app/routers/scoring.py
api/scripts/validate_scoring_api.py
```

Update:

```text
api/app/main.py
```

Do not recreate `LeadScore` unless inspection proves the existing model needs changes.

---

# 37. Recommended Build Sequence

```text
1. Inspect current LeadScore model
2. Confirm PostgreSQL score indexes
3. Run alembic check
4. Decide scoring eligibility policy
5. Decide qualification threshold/policy
6. Decide whether score needs research_id provenance
7. Create scoring schemas
8. Create scoring service
9. Create scoring router
10. Register router
11. Rebuild API
12. Verify routes
13. Test first score
14. Verify PostgreSQL
15. Test second score
16. Verify score history
17. Verify one current score
18. Verify leads.current_score
19. Verify lead_scored event
20. Test error paths
21. Add validation script
22. Run full validation
23. Mark Scoring API complete
```

---

# 38. Database Verification Commands

Inspect table:

```bash
docker exec lorrysystem-postgres psql -U marketing_app -d lorrysystem_marketing -c "\d lead_scores"
```

Inspect indexes:

```bash
docker exec lorrysystem-postgres psql -U marketing_app -d lorrysystem_marketing -c "
SELECT indexname, indexdef
FROM pg_indexes
WHERE tablename = 'lead_scores';
"
```

Check scores:

```bash
docker exec lorrysystem-postgres psql -U marketing_app -d lorrysystem_marketing -c "
SELECT
    id,
    lead_id,
    total_score,
    scoring_version,
    is_current,
    created_at
FROM lead_scores
ORDER BY created_at DESC;
"
```

Compare current scores:

```bash
docker exec lorrysystem-postgres psql -U marketing_app -d lorrysystem_marketing -c "
SELECT
    l.id AS lead_id,
    l.current_score,
    s.id AS score_id,
    s.total_score,
    s.is_current
FROM leads l
LEFT JOIN lead_scores s
    ON s.lead_id = l.id
   AND s.is_current = TRUE;
"
```

---

# 39. Environment Verification

Before coding:

```bash
cd /opt/lorrysystem-marketing
docker ps
```

API:

```bash
docker inspect   --format='{{.State.Health.Status}}'   lorrysystem-marketing-api
```

Expected:

```text
healthy
```

PostgreSQL:

```bash
docker inspect   --format='{{.State.Health.Status}}'   lorrysystem-postgres
```

Expected:

```text
healthy
```

Alembic:

```bash
docker exec lorrysystem-marketing-api alembic current
```

Expected:

```text
d62d40479f83 (head)
```

Synchronization:

```bash
docker exec lorrysystem-marketing-api alembic check
```

Expected:

```text
No new upgrade operations detected.
```

---

# 40. Confirmed Requirements from Existing Project Sources

Existing sources explicitly establish:

```text
lead_scores stores score history
total_score is 0–100
score_breakdown is JSONB
scoring_version is stored
rationale is stored
is_current identifies current score
one current score per lead is enforced
leads.current_score exists
lead_scored is an event type
lead_qualified is an event type
Research completion is separate from qualification
Scoring happens after Research
Scoring happens before Product Matching
n8n must not be integrated yet
```

---

# 41. Requirements NOT Yet Defined by Sources

The existing project sources do not define:

```text
exact scoring formula
category weights
qualification threshold
hard disqualification rules
human override behavior
PARTIAL research eligibility
rescoring rules for terminal leads
whether lead_scores should reference research_id
whether score calculation is internal or initially submitted
```

These must be explicitly decided.

Do not present an invented choice as an established project rule.

---

# 42. Target State Before Product Matching

Scoring API is complete when:

```text
POST score works
score history is preserved
one current score is guaranteed
leads.current_score stays synchronized
range validation works
scoring_version is stored
rationale is stored
lead_scored event is logged
errors are useful
automated validation passes
qualification policy is either implemented and documented
OR explicitly deferred
```

Then proceed to:

```text
Product Matching API
```

---

# 43. Continuation Instruction

Continue from the existing implementation.

Do **not** recreate:

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
Research lifecycle
Research event logging
Migrations 001–003
Research lifecycle migration d62d40479f83
```

Immediate task:

```text
Build and validate the Scoring API.
```

Start by inspecting the current `LeadScore` model and PostgreSQL indexes.

Preserve:

```text
historical score rows
one-current-score invariant
leads.current_score synchronization
event logging
Research/Scoring lifecycle separation
Marketing API ownership of business logic
n8n isolation
```

Do not integrate n8n yet.
