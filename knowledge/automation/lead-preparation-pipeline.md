# Reviewed lead preparation pipeline

For administrator-activated products, [shared product automation](../product/simple-product-onboarding.md) supersedes the manual acceptance/contact/qualification steps described below. Existing unactivated workspaces retain the reviewed workflow. Both modes stop before sending.

Updated: 7 October 2026. Feature branch: `feature/lead-stage-pipeline`.

The implemented sequence is **Research → Contact review → Qualification/scoring →
Product matching → Outreach draft → Approval**. See the version-controlled
[feature guide](../../docs/lead-preparation-pipeline.md) for exact behavior,
endpoints, scoring rubric, deployment, validation and limits.

Administrators/Operators confirm a researched person or an existing company
contact. Source-supported promotion creates/reuses an official Contact and records
the human decision. Changing reviewed identity/contact details requires review
again. Research still never automatically creates contacts.

Run scoring uses current ICP rules and a 100-point evidence rubric. The team
reviews the score and records its qualification decision; that queues matching.
Matching uses only this workspace's active catalog. A selected positive match and
reviewed Email/LinkedIn contact unlock drafting. The worker creates an action and
pending approval in one transaction. Administrators/Reviewers approve, reject or
request changes; Operators/Admins edit returned drafts and resubmit. Nothing sends.

`pipeline-workflows.js` generates a reusable stage child and a separate bound
worker for each workspace. Both reuse current n8n credential references, including
xKiro; provider keys stay in n8n. The worker polls every minute, checks stage API
version 1 and waits safely for application deployment when routes are missing.
Its execution payload retention is disabled. The new queue is Alembic **011**.

DEV published and verified: [stage child](https://n8n-dev.obsidian.cam/workflow/cAm5sRbn3E3hRFv5)
and [minute queue worker](https://n8n-dev.obsidian.cam/workflow/IYUpJtG4ddAfVBpW),
both active at their latest published versions. The worker waits for the API update;
publishing it does not deploy the dashboard/API application.

One running stage per workspace and one active run per lead are enforced. Results
must cite literal quotes from saved research sources. Unknown/foreign products,
stale research/contact/catalog/score context and worker ownership mismatches are
rejected. Completion is transactional/idempotent; failures retain previous results.
Runs older than 30 minutes fail on the next claim; the team explicitly retries.

Validation includes six new JavaScript tests, disposable two-workspace API and
dashboard lifecycle checks, native n8n synthetic-model flows in both workspaces,
provider/evidence/wrong-context failure paths, empty queue/deployment waiting,
database migration/rollback and existing research/workspace regressions. Browser
review exercises the actual forms from contact promotion through revision approval.
All 52 JavaScript tests and eight presentation tests pass. Desktop/mobile browser
tests passed the complete forms sequence, with no overflow or browser errors.

Next work after deployment: calibrate scores and draft quality on real sourced
leads, then define workspace sender accounts and controlled scheduling/delivery.
Budget settings do not enforce provider spend, and approval alone never sends.
