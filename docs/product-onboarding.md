# Product setup and shared automation

Administrators describe a product and enter its real offerings in **Product Setup**. Activation prepares customer profiles and a discovery search, then automatically runs lead preparation through a draft awaiting human approval. Product teams do not configure n8n templates, enter provider keys or choose internal catalog identifiers.

Platform administrators create private product workspaces and assign their administrators. Workspace administrators activate, pause, resume and explicitly retry interrupted jobs. Operators can request another discovery batch and resolve lead/contact issues. Reviewers and administrators retain approval decisions. Sending is a separate feature: neither activation nor approval sends a message.

## Product form

Enter the product type, a description of its problems/capabilities, and at least one offering with its actual capabilities. Target customers are optional. Country, language, brand voice and a daily batch size are preferences. The initial form offers nine country presets; the API accepts two-letter country codes. The catalog remains authoritative; generated customer targeting does not create product features.

**Activate product** queues configuration. Generated profiles/search appear under Prepared targeting. Jobs and failures appear under Automation activity. The worker discovers up to five suitable new companies per daily batch by default; administrators can choose 1–10. Find Leads can request an extra bounded batch without configuring a webhook. The daily timer moves forward after an explicit batch, so it does not immediately duplicate that request.

Current preparation policy:

1. Fetch public pages through the existing guarded fetcher. Search snippets alone cannot create a candidate. Skip workspace candidate/company domains already known.
2. Accept a company only when fetched evidence supports its identity and an active workspace ICP with confidence ≥75%. Acceptance, the pending research job and the shared job association commit together.
3. Research the company and public professional contacts; retain source links, literal supporting quotes, confidence, unknowns and conflicting profiles.
4. Select a supported, reachable business contact. A general mailbox alone does not create a named person. Missing supported contacts stop at Needs review.
5. Apply the existing five-part evidence scoring rubric. Qualification requires score ≥60/100 and positive evidenced ICP fit. Unknown buying intent earns no points.
6. Match only current workspace catalog products. A match ≥60/100 can produce an email draft, or an individual LinkedIn message draft if only a supported LinkedIn profile is available.
7. Create one outreach draft and pending human approval. The worker cannot approve, edit approval decisions or send messages.

Low scores or unsupported matches retain findings and stop automatic progression. They do not invent fit or close a lead. Manual review controls remain available under an advanced disclosure. New managed acceptance and requested research/stage runs enter the shared queue; historical completed leads are not automatically reprocessed.

Pause stops claims and immediately blocks in-flight business requests. A worker finishing after pause records a paused failure; resume continues pending jobs. Failed jobs require an explicit Retry or continue. Completed research missing a contact can continue after a supported business contact is reviewed. Setup/catalog changes wait for outstanding preparation jobs to finish. Failure retries never run on an automatic spending loop.

## Shared worker access

Alembic **012** adds workspace-owned `product_automation_plans` and `automation_jobs` under forced RLS, plus the platform control table `automation_workers`. The root worker key is hashed in the control database and cannot read ordinary business APIs. It can only authenticate the worker health, claim and finish control endpoints.

A claim returns one job, its workspace UUID and a random 30-minute lease. Business requests require all three: the named root credential, `X-Automation-Lease`, and the exact `X-Workspace-ID`. The API checks worker revocation, workspace activity, enabled product, job status/expiry, and a route allowlist restricted to that job’s native research or stage UUID. RLS still scopes business database queries. Only queue metadata uses privileged control sessions.

One job runs per workspace; different products can run concurrently. Claims serialize scheduler decisions and use database locks. Finishing is serialized per job and idempotent. Lease expiry marks the native job failed as well, allowing explicit retry. Approval/sending endpoints are excluded from every lease. Audit events distinguish automatic contact selection and the shared service actor from human decisions.

The shared n8n graph set is fixed: **Product Setup**, **Company Discovery**, **Company and People Research**, **Qualification and Outreach Preparation**, and one scheduled queue dispatcher. Each receives current job/workspace context. Discovery memory is database-owned, without per-product n8n Data Tables. Legacy research/stage workers cannot claim managed products, including paused ones. The legacy workspace preflight contract also stops bound discovery graphs before search/model calls when a product is managed; only job leases satisfy the shared contract.

## One-time platform connection and release

Merge/deploy the API and dashboard through the normal develop CI/CD pipeline; migration 012 must be applied. Before activating products in DEV, platform operations makes this one-time connection:

1. Sign in as a platform administrator with workspace ADMIN access. In **Settings → Connections → Platform automation connection**, create a shared worker credential. Copy its one-time token into **n8n Header Auth**, header `X-API-Key`. Do not use a named single-workspace key for this role. Root keys can be listed/revoked through platform-admin `/api/automation/workers` endpoints.
2. Use the existing Brave and xKiro n8n credentials. Provider secrets remain in n8n, not the API environment or workflow JSON.
3. Fill `integrations/n8n/shared-binding.example.json` with credential **references**, not key values. `node integrations/n8n/shared-workflows.js children BINDING.json CHILDREN.json` generates four inactive child definitions. Import each value from CHILDREN.json as its own workflow and activate the child versions. Save their IDs as `{setup,discovery,research,pipeline}`.
4. `node integrations/n8n/shared-workflows.js worker BINDING.json WORKER.json CHILD_IDS.json` generates the dispatcher. Import and activate it. It polls every minute; a missing API version makes it wait before any provider work. Bad credentials or server errors stop it instead of consuming provider calls.
5. Disable successful/error/manual execution retention on these workflows: the generated settings already use `none`/`false` to avoid persisting ephemeral leases. Product teams then use only the application’s setup form.

Existing unactivated workspaces retain reviewed legacy integrations. Once a workspace is activated for managed automation, its old worker cannot claim its queues. Turning off managed automation does not silently restore the old worker.

## Validation

`api/scripts/validate_product_automation.py` runs against disposable PostgreSQL/API only. It covers two unrelated catalogs, automatic sourced acceptance, the whole preparation path, pending approval, wrong-workspace/native-route access, root-key isolation, idempotence, pause, expiry and explicit retries. The existing workspace, discovery, research, migration and reviewed-pipeline regressions remain required. `integrations/n8n/shared.test.js` checks dynamic contexts, bounded discovery, exact quotes, credential references, provider failure sanitization and no sending nodes/lease retention.

Native n8n testing used the real disposable API and mocked search/web/model providers for both fleet and accounting products. All six jobs completed through one shared graph set, drafts remained pending approval, empty queues made no provider calls, and an outage required explicit retry. Desktop/mobile browser tests covered workspace creation, catalog form controls, activation, pause/resume and hidden advanced integration settings. No live provider spending or server deployment is implied by these tests.

## Live DEV activation — 7 October 2026

The deployed API passed the shared-worker health check. The named `Shared Product Worker DEV` credential is connected, and all four shared children plus the minute dispatcher are active. LorrySystem was activated through the existing product form, preserving its six catalog entries and limiting discovery to one new company per daily batch. Other products were not activated by this test.

The first live run exposed three provider interoperability issues: setup/discovery JSON can arrive inside Markdown fences; Brave requires an explicit JSON Accept header; and simultaneous named-person requests can return HTTP 429. The generators now accept fenced JSON without relaxing schema/evidence validation, declare the header, and space research/profile searches 1.5 seconds apart. Official leadership searches receive priority within the existing six-page fetch budget, avoiding service results crowding out named-person evidence. Profile identity must appear in the result title, so incidental mentions in another person's snippet cannot create a contact match. Failed jobs were explicitly retried; no automatic failure-spending loop was added.

Stage extraction retains strict catalog/rubric and source validation. Citation instructions now ask for a short contiguous excerpt copied from the exact source evidence. Rejected scoring/matching/drafting outputs report sanitized codes distinguishing schema, citation count, source URL, quote length and quote mismatch. Raw model responses and lease proofs are not retained. A rejected first score was explicitly retried and completed at 65/100; unknown scale and buying signals received zero points.

Live sourced test passed: [Quanterm Logistics](https://dashboard-dev.obsidian.cam/leads/256fe94a-3a09-4b59-8846-d61e88f040e8), discovered from quanterm.com. Official leadership evidence and public name/company matches support Michael Soh and Titi Nguyễn's individual LinkedIn profiles. Automatic contact selection chose Michael Soh; qualification/scoring completed at **65/100** (unknown fleet size and buying signals earned zero), then catalog matching returned **GPS 90/100** and **TMS 80/100**. Undocumented/unsupported offerings stayed at zero. One GPS LinkedIn draft was created because no named business email was verified. [Approval f336a329-fae2-4d22-aba9-9af309973af4](https://dashboard-dev.obsidian.cam/approvals/f336a329-fae2-4d22-aba9-9af309973af4) was verified **PENDING**, with outreach **PENDING_APPROVAL**. No approval or sending action was performed.

This was a repaired live integration test, not a clean first-run pass. Setup, search, contact coverage and model citations initially stopped safely; explicit retries followed the corrections. Three earlier research attempts remain Needs review in historical job records; they were not retried after newer research succeeded, avoiding duplicate stage work. Current preparation completed. These stale historical warnings are a follow-up UI issue. LorrySystem remains active with the one-company daily cap; AIPath was untouched. Capability fit is advisory and does not establish purchase intent; a reviewer should assess the GPS draft against the company's existing tracking setup.
