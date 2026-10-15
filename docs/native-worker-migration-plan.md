# Native worker migration plan

Status: planned on 11 October 2026. This document describes the next implementation milestones; it does not claim that replacement stages are complete or deployed.

Implementation update: the shared native stage handlers, scheduling/API controls, source validation, provider reservations and pending approval path are implemented locally. See [native preparation workers](native-preparation-workers.md) for verified scope and limitations. Encrypted provider management, real-provider calibration, dashboard/data migration, sending parity and executor cutover remain outstanding.

Parallel DEV rollout update: the root Compose file now includes the native API/database/worker stack and a separate single-process native dashboard on loopback ports 8020/8093. It does not migrate legacy data or stop n8n. See [native DEV cutover runbook](native-dev-cutover.md) for server configuration and release gates. The deployment helper must start all included services; verify its exact service selection before merging/deploying. Native dashboard sessions remain process-local, so this is validation infrastructure, not a horizontally scalable production cutover.

## Outcome and boundaries

Replace n8n execution with one shared Python preparation pipeline driven by each workspace's product form, real catalog, targeting, preferences and policy. Administrators create and activate products; operators request discovery and resolve exceptions. Normal preparation advances automatically to a draft pending human approval. Approval never sends. Sending remains a separate explicit stage.

Keep FastAPI, PostgreSQL, the existing durable queue, worker leases and workspace isolation. Do not introduce another workflow service for this milestone. Reuse audited business rules and public-fetch protections, while translating the n8n orchestration into Python handlers. Do not copy secrets or import the legacy API into the new backend.

The current deployed application still depends on n8n. The replacement database is independent and dashboard, data and credential migration remain necessary before retiring it.

## 1. Pipeline contracts, providers and persistence

The current worker only dispatches RESEARCH, every job requires a lead, and completion unconditionally stops at contact review. Extend these contracts before adding handlers:

- Separate workspace-level setup/discovery jobs from lead-level preparation jobs, with database checks for each job kind and workspace ownership.
- Add preparation runs and stage records, typed result schemas, source records, candidates/discovery memory, researched people, selected contacts, assessments, matches, drafts and immutable approval snapshots. Add forced workspace policies, composite foreign keys and explicit grants to new tables.
- Atomically persist each validated result and enqueue its next eligible stage. Unique stage keys and active-run constraints prevent duplicate progression. Completion must require a valid lease, current context and an active product. Restarted workers resume saved stage checkpoints.
- Version/hash the catalog, targeting, research and selected contact context. Edits invalidate stale downstream work and approval readiness; preserve historical results.
- Add a handler registry and a database-backed scheduler for activated products. Pause blocks new claims and in-flight completion; resume does not silently restart permanently failed work.
- Centralize Brave Search and xKiro clients, structured output parsing, pacing, bounded transient retries, provider health and usage accounting. Stable sanitized codes distinguish provider failure, budget exhaustion, coverage gaps and human review stops.
- Use centrally managed provider credentials, resolved only by the trusted worker. Platform operators configure providers once; product teams never need n8n or provider keys. Private development configuration can bootstrap adapters; encrypted credential management and rotation are required for the cutover.
- Reserve bounded provider allowance before requests, count retries and record actual reported tokens or explicitly estimated usage. Unknown transport outcomes remain recorded; do not promise exactly-once provider billing or exact costs when pricing/usage is unavailable.

Acceptance: PostgreSQL tests demonstrate concurrent claims, duplicate completion, atomic result/next-job creation, workspace isolation, pause, catalog edits, lease expiry and recovery without duplicate drafts or orphaned transitions. Existing foundation tests must remain green.

## 2. Product setup and discovery

Prepare targeting/search plans from the administrator's form and authoritative catalog. Preserve manually supplied ICPs; generated targeting cannot invent product capabilities. Support activate, pause, resume and manual bounded discovery requests, plus scheduled batches.

Use Brave to find candidate domains and fetch official company evidence through the guarded fetcher. Canonicalize identity/domain conservatively and retain workspace discovery memory, rejected candidates and decision reasons. Search snippets alone cannot create an accepted company. Auto-accept only sourced, identity-verified candidates that meet the configured ICP policy; atomically create the lead and preparation run. Zero suitable results is a successful empty batch.

Initial live acceptance batches are at most three companies per product. Keep independent caps for search requests, fetched pages and candidates; requesting three accepted companies must not permit unlimited searching.

Acceptance: duplicate domains, repeat batches, empty results, unsupported identities, throttling, budgets and two unrelated catalogs remain isolated and bounded.

## 3. Deeper research and professional contacts

Expand the homepage handler to bounded official About, Services, Contact, Leadership and relevant supporting pages. Start with the existing six-page research budget, prioritize contact/leadership coverage and persist fetched pages before model calls. Record company identity, sourced industry, services, fleet/scale clues, existing technology, observed needs, buying signals, confidence, conflicting information and explicit unknowns.

Extract only publicly supported business contacts. Search publicly indexed LinkedIn and relevant professional handles for named people whose company relationship is supported. Do not turn a generic mailbox into a named individual. Ambiguous identity/profile matches stay unresolved. Public profile search needs no platform login.

Under automatic policy, select only a sufficiently supported, reachable contact. Otherwise stop with a specific reason and available resolution action: add/confirm a sourced contact, select among supported identities, retry an unavailable search or use an eligible alternate channel. Continuing after resolution must reuse valid research, avoiding a full expensive restart.

Acceptance: sources and exact quotes are validated; industry persists with attribution; ambiguous names, absent contacts, robots restrictions and partial provider outages are represented honestly. A research result does not always require human review if the automatic contact policy is satisfied.

## 4. Qualification and product matching

Port the latest corrected scoring rules rather than historical n8n test scores. Keep advisory ICP/capability relevance separate from observed buying opportunity. Use the existing five-component rubric as the default, with validated workspace rubric overrides.

Operational-need points require observed PAIN_POINT evidence; buying-signal points require observed SIGNAL evidence. Existing GPS, CRM or other systems establish capability context, not an unmet need. Unknowns receive no unsupported positive points and remain distinguishable from negative fit. Totals are computed from validated components.

Apply the current managed-product qualification policy by default: score at least 60 and positive evidenced ICP fit. These thresholds are configurable policy, not proof of purchasing intent. Below-threshold leads retain their research and a clear reason for stopping. Match only the current active workspace catalog, with evidence and capability references; preserve the current match threshold of 60 for automatic drafting unless policy changes explicitly.

Acceptance: the same company can fit one catalog and fail another; existing systems do not inflate opportunity; invented products, unsupported quotes, stale results and invalid rubrics cannot advance the pipeline. Include the Quanterm existing-GPS case as a calibration regression.

## 5. Outreach drafts and pending approval

Draft using current research, supported contact, selected match, real product capabilities, workspace voice and language. Prefer the eligible configured channel; email requires a supported email address and LinkedIn requires a supported individual profile. A draft does not claim guaranteed improvement, fabricate needs, invent sender identity or imply an existing solution is inadequate without evidence.

Persist draft plus pending approval and immutable input snapshot in one transaction. Worker credentials cannot approve or send. Bind review to current research, contact, catalog, score and match; changed context makes the draft stale and requires regeneration/review. Add approval/rejection/request-change API operations with role checks, audit history and revision snapshots so a draft can be reviewed later through the dashboard.

Acceptance: one pending draft/approval per eligible run, no duplicates on retries, no approval bypass, no sending side effect and stale-input rejection. Compare relevance, tone and repetition across the test batch; structural validation alone cannot establish good prose.

## 6. End-to-end validation and executor cutover

Start with mocked-provider PostgreSQL and running API/worker tests. Exercise the whole pipeline across LorrySystem and a clearly labelled fictional AIPath catalog, using distinct workspace data and expectations. Fault-inject provider throttling, malformed output, worker loss, budget exhaustion, catalog edits, pause and contact gaps.

Then run bounded real preparation for up to three companies per product with centrally configured providers. Report coverage, stop reasons, score components, match relevance, draft quality and usage per lead. Real leads may correctly stop before drafting if evidence/contact/qualification is insufficient; successful completion must never be forced by invented inputs.

Before retirement, connect the dashboard to the replacement contracts, expose current stage/review reasons/history and provider usage, and migrate required accounts, catalog, leads, evidence, approval history and credential references through a dry-run import with reconciliation. Port the existing SMTP safeguards before routing separate sending to the new backend; real SMTP testing remains deferred until the user resumes it.

Select exactly one active executor per workspace. Disable/drain old n8n ownership before enabling the new executor against equivalent live data; the separate local database is not itself a cutover. Verify rollback can restore the old executor without duplicate preparation or messages.

Legacy API preflight receives the legacy workspace UUID, while ownership rows live in the native database. It must resolve `legacy_identity_map` before checking a capability. A missing identity mapping fails closed and prevents a reliable rollback. Do not mark reconciliation complete or activate Python until the legacy workspace, catalog, pending jobs and active leases have been reconciled with the mapped native workspace.

PRs always target `develop`; local acceptance precedes DEV release. Production release is a separate decision. Do not disable n8n until parity, migration, dashboard readiness and executor ownership are verified.

## Progress reporting

After each implemented milestone, update its feature documentation, the local knowledge base and the acceptance evidence. State whether results came from mocked providers, real providers, local execution or DEV. Plan documentation is not deployment confirmation.

Next implementation: milestone 1 contracts and provider foundation, followed by native product setup/discovery. See [current backend scope](../backend/README.md).
