# Lead preparation: research through approval

Implemented 7 October 2026. This feature builds on workspace-aware discovery,
company research and people-profile search. The dashboard uses FastAPI, Jinja2,
custom CSS and vanilla JavaScript; n8n runs the bounded model jobs.

## Team workflow

Administrator-activated products now use [shared product automation](product-onboarding.md):
the system accepts sourced candidates, selects supported contacts, qualifies under
the configured automatic policy, matches and drafts through pending human approval.
The steps below describe the manual controls and unactivated legacy workspaces.
Sending remains separate in both modes.

1. **Research.** Accept a discovered candidate to create an official lead and its
   research job. The existing research worker collects public company evidence,
   supported people and professional profiles. Existing leads can rerun research.
2. **Contact review.** An Administrator or Operator reviews a researched person's
   company relationship, role and profile, checks the confirmation box and chooses
   **Use as primary contact**. Alternatively, confirm an existing company contact
   in the Contact review & qualification panel. Research alone never promotes a
   person to an official contact. Conflicting LinkedIn identities stay unresolved
   unless the reviewer selects a supported candidate.
3. **Qualification/scoring.** Choose **Run scoring**. The workspace worker assesses
   the current research against this lead's ICP and saves score criteria,
   rationale, quotes and missing information. The team reviews the result, enters
   a qualification note and chooses **Qualify & match products**. Scores are
   advisory; there is no automatic qualification or disqualification threshold.
4. **Product matching.** The worker evaluates only active products in this
   workspace. It saves fit scores, explanations and supporting evidence. A
   qualified lead can refresh its matches. Unsupported products cannot be saved.
5. **Outreach draft.** Select a positively matched product and Email or LinkedIn
   message draft. Email needs a confirmed contact email; LinkedIn needs a reviewed
   individual profile. The worker uses the selected product, reviewed contact,
   research evidence and workspace brand voice. It creates an action and a pending
   approval request in one transaction.
6. **Approval.** Open the action's approval link. Administrators and Reviewers can
   approve, reject or request changes. Changes return the action to Draft; an
   Administrator or Operator can edit it on the lead page and request approval
   again. Earlier approval snapshots remain immutable history. Approval does not
   schedule or send a message.

The lead page displays six stage links, the company/contact overview above the
research brief, stage controls, readable score criteria, matches, actions and
approval history. Queued/running stages refresh every 15 seconds while the page
is visible, unless a form is being edited or a dialog is open. Failed runs retain
previous results and can be retried from the appropriate stage control.

## Evidence and scoring policy

The default rubric totals 100 possible points:

| Criterion | Maximum |
| --- | ---: |
| ICP fit | 40 |
| Operational need | 30 |
| Operating scale | 15 |
| Buying signals | 10 |
| Evidence quality | 5 |

Each positive component and positive product fit requires at least one literal
quote from a saved source in the selected research run. Missing evidence earns
zero points, with unknowns recorded separately from negative fit. The API checks
the entire output before persisting any score or match. It calculates the total
from validated integer components; the model does not set the lead's status.

An ICP may supply `qualification_rules.scoring_rubric`: one to ten entries with
distinct snake_case `criterion` codes, positive integer `max_points` totaling 100,
and optional `label`/`description`. Otherwise the default rubric is used.
Research confidence and advisory qualification score are separate concepts.

Contact promotion checks saved names, roles, company association and literal
email/phone evidence. A selected LinkedIn profile must come from saved researched
profiles and supporting sources. Existing company contacts may be confirmed by
the team without a new person extraction. Changing reviewed contact details
requires review again. Contact records are reused when identity/email evidence
matches, and contacts from another company or workspace cannot be selected.

Model/source content is untrusted. Prompts forbid invented facts, product
capabilities, prices, guarantees, sender identities and buying intent. Structured
validators enforce catalog membership, schema/size bounds, URLs and exact saved
quotes. Human review remains necessary to assess interpretation and prose.

## API and storage

Alembic revision **011**, after 010, adds `lead_pipeline_runs`. Its rows belong to
one workspace, use composite workspace foreign keys for lead/research/contact,
and have forced row-level security under the restricted runtime role. An active
run is unique per workspace/lead. History records stage, actors, input snapshot,
result identifiers, timestamps and sanitized failure codes.

| Route | Purpose |
| --- | --- |
| `POST /api/leads/{id}/contact-review` | Human confirmation of an existing contact or sourced research person |
| `POST /api/leads/{id}/qualify` | Human qualification note and atomic matching request |
| `POST /api/leads/{id}/pipeline` | Human request for SCORING, MATCHING or DRAFTING |
| `GET /api/leads/{id}/pipeline` | Workspace-scoped run history |
| `GET /api/leads/{id}/pipeline-state` | Current review/score/match readiness for dashboard controls |
| `GET /api/pipeline/health` | Versioned deployment readiness, including table availability |
| `POST /api/pipeline/claim` | Named service claims the oldest pending workspace job |
| `GET /api/pipeline/{id}/context` | Claimed worker obtains verified stage context |
| `PATCH /api/pipeline/{id}/complete` | Validate output and commit results plus completion atomically |
| `PATCH /api/pipeline/{id}/fail` | Claimed worker records a sanitized failure code |

Human preparation decisions require Administrator/Operator roles. Worker routes
require named service credentials, and a run can only be completed by its claiming
worker. Approval decisions retain the existing Administrator/Reviewer policy.
Dashboard mutations require CSRF and verify that edited drafts belong to the lead.

One stage runs per workspace at a time. Claiming marks running jobs older than
30 minutes failed with `WORKER_TIMEOUT`; retry is explicit. Repeated completion
returns the existing result without duplicating a score/action/approval.
Completion and result persistence share one database transaction. Existing
service entry points keep their original default commit behavior.

Queued work is tied to current usable research, primary contact, ICP/catalog
content and, for matching/drafting, the current score. Changes invalidate stale
work before model invocation or completion. Drafting also checks the selected
product match and channel. A new research run or score requires fresh product
matching before drafting. Historical scores, matches and actions remain visible.

## n8n setup and deployment

`integrations/n8n/pipeline-workflows.js` generates two inactive workflows from a
binding containing a fixed workspace UUID/internal API origin, named Marketing
API credential reference and custom model credential reference. Use a separate
binding/pair for each product workspace; workflow code is shared.

```bash
node integrations/n8n/pipeline-workflows.js child \
  tmp/stage-binding.json tmp/stage-child.json
node integrations/n8n/pipeline-workflows.js worker \
  tmp/stage-binding.json tmp/stage-worker.json CHILD_WORKFLOW_ID
```

The binding's `llm` uses the existing xKiro Header Auth credential, HTTPS base
`https://api.xkiro.com/v1`, model `mistralai/mistral-large-2512`, provider `xkiro`
and `max_tokens: 6000`. Only credential `id` and `name` are stored in exports.
Provider keys remain in n8n, not the API environment or Code nodes.

The worker polls every minute, loads current workspace context, verifies the
stage API version and claims a job before invoking the child. A missing old API
route (404/405) waits for deployment without model calls. Authorization and server
errors stop the worker. The child validates stage context, calls `/chat/completions`,
validates structured output and completes the job; failures return a sanitized
code to the parent. Provider errors and raw model bodies are not stored as
dashboard records. Execution payload retention is disabled in published DEV pairs.

Publish the child before activating the worker. Deploy the application through
the user's normal **PR merge into develop → CI/CD DEV deployment** path; migration
011 must be applied before stage requests work. The new worker can be published
in advance because its health gate waits for that API update. Do not activate
the old unadapted scoring/matching/drafting/sender exports alongside this queue.

DEV publishing verified 7 October 2026: [stage child](https://n8n-dev.obsidian.cam/workflow/cAm5sRbn3E3hRFv5)
and [queue worker](https://n8n-dev.obsidian.cam/workflow/IYUpJtG4ddAfVBpW).
Both are active at their current published versions, use the existing workspace
API/xKiro credential references, and disable execution payload retention. The
application change remains pending the user's develop merge/deployment.

## Validation and limits

- `api/scripts/validate_lead_pipeline.py` runs only in `ci`/`workspace-test`, using
  two disposable workspaces. It covers contact review, evidence rejection,
  concurrent claims, workspace isolation, scoring, qualification, catalog matching,
  transactional/idempotent drafts and approvals, revision history, stale context,
  timeout recovery, dashboard controls, CSRF and Viewer restrictions.
- `integrations/n8n/pipeline.test.js` checks context/output validators, schema and
  evidence bounds, provider sanitization, credential binding and Code sandbox
  compatibility. Existing discovery/research/profile tests remain in CI.
- Native n8n 2.41.7 checks use the real disposable API with synthetic model
  responses: two workspace flows, deployment waiting, empty queues, provider
  failure, unsupported quotes and wrong child context. These incur no provider
  charges and do not validate real-model output quality.
- Desktop/mobile browser checks exercise contact promotion through approval,
  including request changes, editing/resubmission and overflow/browser errors.
  Migration and existing workspace/research regressions remain required.

The feature ends at approval. Sender credentials, scheduling, delivery and
replies are later work. Workspace budget settings are not enforced provider-spend
caps. Existing qualified leads with legacy scores need a fresh reviewed-contact
score and current pipeline matches before using the new drafting control. Small
bounded catalogs (one to thirty active products) are supported; missing or
oversized catalogs stop preparation. Score quality depends on evidence and the
workspace ICP/product descriptions, so teams should calibrate it on real leads.
